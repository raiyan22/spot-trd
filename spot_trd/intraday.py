"""Pre-registered intraday BTC/USDT study: does a predefined strategy have positive expectancy after realistic costs?

Strategies, costs, sample and acceptance criteria are written in reports/intraday_preregistration_2026-10-02.md BEFORE this
module or any intraday data existed. The constants below transcribe them; do not tune them after seeing results.
Run: uv run python -m spot_trd.intraday
"""
import hashlib
import json
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from spot_trd.audit import longest_streak, pct, table
from spot_trd.config import RAW_DIR, REPORTS_DIR, ROOT, load_rules
from spot_trd.data import load_data
from spot_trd.indicators import atr, ema, rsi
from spot_trd.regime import build_features
from spot_trd.sizing import round_down

# ---- pre-registered constants ------------------------------------------------------------------------------------------
START = pd.Timestamp("2018-03-04")
HALF_SPLIT = pd.Timestamp("2022-07-01")
MIN_NOTIONAL, QTY_STEP, RISK, CASH_CAP = 5.5, 0.00001, 0.01, 0.98
LAST_ENTRY_OPEN_HOUR, FORCE_EXIT_HOUR = 20, 23
N_STRATEGIES = 3
MIN_TRADES = 300
CAGR_MIN, DD_MAX = 0.05, 0.15
COST_MARGIN_MIN, YEARS_POSITIVE_MIN = 1.5, 6
PLACEBO_RUNS, PLACEBO_PCTL = 200, 0.95


@dataclass(frozen=True)
class Costs:
    fee: float
    slip: float          # market entries and exits
    stop_slip: float     # below the stop or the open, whichever is lower
    pen: float           # limit targets fill only if price trades through by this much


COSTS = {"base": Costs(0.001, 0.0005, 0.001, 0.0005), "harsh": Costs(0.001, 0.0015, 0.003, 0.0015)}


# ---- signals ---------------------------------------------------------------------------------------------------------------

@dataclass
class Signals:
    sig: np.ndarray          # decided at this candle's close; executes at the NEXT open
    stop: np.ndarray
    target: np.ndarray
    ema_exit: np.ndarray     # close-based exit flag: sell at the next open


def daily_from_hourly(h1: pd.DataFrame) -> pd.DataFrame:
    d = h1.resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    return d


def day_gate(daily_series: pd.Series, index: pd.DatetimeIndex) -> np.ndarray:
    """Value of the PREVIOUS completed day for every hourly candle: day D's value is known only after D closes."""
    prev = daily_series.shift(1)
    return prev.reindex(index.normalize()).fillna(False).to_numpy(dtype=bool)


def build_signals(h1: pd.DataFrame, name: str, gate: np.ndarray | None = None) -> Signals:
    n = len(h1)
    o, h, l, c = (h1[k].to_numpy() for k in ("open", "high", "low", "close"))
    hour = h1.index.hour.to_numpy()
    nan = np.full(n, np.nan)
    stop, target, ema_exit = nan.copy(), nan.copy(), np.zeros(n, bool)
    gate = np.ones(n, bool) if gate is None else gate
    cls = pd.Series(c, index=h1.index)
    if name == "A":
        day = h1.index.normalize()
        early = pd.Series(hour <= 3, index=h1.index)
        rng_hi = pd.Series(h, index=h1.index).where(early).groupby(day).transform("max")
        rng_lo = pd.Series(l, index=h1.index).where(early).groupby(day).transform("min")
        cnt = early.groupby(day).transform("sum")
        ok = (hour >= 4) & (hour <= 19) & (cnt.to_numpy() == 4) & (c > rng_hi.to_numpy()) & \
             ((rng_hi.to_numpy() - rng_lo.to_numpy()) / rng_hi.to_numpy() >= 0.005)
        okS = pd.Series(ok, index=h1.index)
        first = ok & (okS.groupby(day).cumsum().to_numpy() == 1)
        sig, stop = first, rng_lo.to_numpy()
    elif name == "B":
        e20, e50 = ema(cls, 20).to_numpy(), ema(cls, 50).to_numpy()
        a14 = atr(h1[["open", "high", "low", "close"]], 14).to_numpy()
        below = pd.Series(c < e20, index=h1.index).astype(float).rolling(8).max().to_numpy() > 0
        sig = below & (c > e20) & (e20 > e50) & (c > o) & gate & (hour <= 19)
        stop = pd.Series(l, index=h1.index).rolling(8).min().to_numpy() - 0.5 * a14
        ema_exit = c < e50
    elif name == "C":
        mid = cls.rolling(20).mean()
        sd = cls.rolling(20).std(ddof=0)
        lower = (mid - 2 * sd).to_numpy()
        r14 = rsi(cls, 14).to_numpy()
        a14 = atr(h1[["open", "high", "low", "close"]], 14).to_numpy()
        tgt = mid.to_numpy()
        sig = (c < lower) & (r14 < 30) & gate & (hour <= 19) & ((tgt - c) / c >= 0.004)
        stop, target = c - 1.5 * a14, tgt
    else:
        raise ValueError(name)
    sig = np.nan_to_num(sig, nan=0).astype(bool) & ~np.isnan(stop)
    return Signals(sig, stop, target, ema_exit)


# ---- simulator -------------------------------------------------------------------------------------------------------------

@dataclass
class Trade:
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry_px: float
    exit_px: float
    qty: float
    gross: float        # un-slipped price move
    ret: float          # net return on cost basis after fees and slippage
    unit_risk: float    # planned risk fraction: stop distance + round-trip cost
    pnl: float
    fees: float
    slip: float
    reason: str

    @property
    def R(self) -> float:
        return self.ret / self.unit_risk


def simulate(h1: pd.DataFrame, s: Signals, costs: Costs, capital: float, leak: bool = False) -> dict:
    o, h, l, c = (h1[k].to_numpy() for k in ("open", "high", "low", "close"))
    hour, dayn = h1.index.hour.to_numpy(), h1.index.to_numpy().astype("datetime64[D]").astype("int64")
    n = len(h1)
    fee, slip, sslip, pen = costs.fee, costs.slip, costs.stop_slip, costs.pen
    cash, qty = capital, 0.0
    stop = target = entry_ref = cost_basis = 0.0
    entry_i = -1
    last_day, exit_next = -1, False
    trades, equity, skipped = [], np.empty(n), 0
    ef = es = 0.0
    for j in range(n):
        # 1. entry decided at the previous close (or, for the leak detector only, at this candle's own close)
        src = j if leak else j - 1
        if qty == 0 and src >= 0 and s.sig[src] and dayn[j] != last_day and 1 <= hour[j] <= LAST_ENTRY_OPEN_HOUR:
            px = o[j] * (1 + slip)
            st = s.stop[src]
            if st < px:
                stop_frac = (px - st) / px
                unit = stop_frac + 2 * fee + 2 * slip
                notional = min(RISK * cash / unit, CASH_CAP * cash / (1 + fee))
                q = round_down(notional / px, QTY_STEP)
                if q * px >= MIN_NOTIONAL:
                    cost_basis = q * px * (1 + fee)
                    cash -= cost_basis
                    qty, stop, target, entry_i, entry_ref = q, st, s.target[src], j, o[j]
                    last_day, exit_next = dayn[j], False
                    ef, es = q * px * fee, q * (px - o[j])
                    entry_unit = unit
                else:
                    skipped += 1
        # 2. exits
        if qty > 0:
            fill, reason, fee_x, slip_x = None, None, 0.0, 0.0
            started_before = entry_i < j
            if started_before and (hour[j] == FORCE_EXIT_HOUR or dayn[j] != last_day or exit_next):
                fill, reason = o[j] * (1 - slip), "time" if not exit_next else "signal"
                ref = o[j]
            elif l[j] <= stop:
                ref = min(stop, o[j])
                fill, reason = ref * (1 - sslip), "stop"
            elif not np.isnan(target) and (o[j] >= target or h[j] >= target * (1 + pen)):
                ref = max(target, o[j]) if o[j] >= target else target
                fill, reason = ref, "target"
            if fill is not None:
                proceeds = qty * fill * (1 - fee)
                cash += proceeds
                fx = qty * fill * fee
                sx = qty * max(ref - fill, 0.0)
                trades.append(Trade(h1.index[entry_i], h1.index[j], o[entry_i], fill, qty, ref / entry_ref - 1,
                                    proceeds / cost_basis - 1, entry_unit, proceeds - cost_basis, ef + fx, es + sx, reason))
                qty = 0.0
            elif s.ema_exit[j]:
                exit_next = True
        equity[j] = cash + qty * c[j]
    return {"trades": trades, "equity": pd.Series(equity, index=h1.index), "skipped": skipped}


# ---- statistics ------------------------------------------------------------------------------------------------------------

def week_bootstrap(trades: list[Trade], n: int = 10_000, seed: int = 9) -> dict:
    """One-sided block bootstrap of mean net R, blocks = calendar weeks of the exit date."""
    if len(trades) < 5:
        return {"lo": float("nan"), "p": float("nan")}
    df = pd.DataFrame({"w": [t.exit_time.to_period("W") for t in trades], "R": [t.R for t in trades]})
    g = df.groupby("w")["R"].agg(["sum", "count"])
    s, k = g["sum"].to_numpy(), g["count"].to_numpy()
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(s), size=(n, len(s)))
    means = s[idx].sum(axis=1) / k[idx].sum(axis=1)
    return {"lo": float(np.percentile(means, 100 * (1 / N_STRATEGIES) * 0.05)), "p": float((means <= 0).mean())}


def stats(trades: list[Trade], eq: pd.Series, capital: float) -> dict:
    n = len(trades)
    R = np.array([t.R for t in trades])
    ret = np.array([t.ret for t in trades])
    gross = np.array([t.gross for t in trades])
    pnl = np.array([t.pnl for t in trades])
    years = (eq.index[-1] - eq.index[0]).days / 365.25
    d = eq.resample("1D").last().dropna()
    dr = d.pct_change().dropna()
    gains, losses = pnl[pnl > 0].sum(), -pnl[pnl < 0].sum()
    cost = (gross - ret).mean() if n else float("nan")
    return {
        "n": n, "per_year": n / years, "win": float((ret > 0).mean()) if n else float("nan"),
        "gross": float(gross.mean()) if n else float("nan"), "ret": float(ret.mean()) if n else float("nan"),
        "cost": float(cost), "R": float(R.mean()) if n else float("nan"), "medR": float(np.median(R)) if n else float("nan"),
        "pf": float(gains / losses) if losses > 0 else float("inf"),
        "streak": longest_streak(list(ret < 0)), "margin": float(gross.mean() / cost) if n and cost > 0 else float("nan"),
        "final": float(eq.iloc[-1]), "cagr": float((eq.iloc[-1] / capital) ** (1 / years) - 1) if eq.iloc[-1] > 0 else -1.0,
        "dd": float((eq / eq.cummax() - 1).min()), "profit_py": float((eq.iloc[-1] - capital) / years),
        "sharpe": float(np.sqrt(365) * dr.mean() / dr.std()) if dr.std() > 0 else float("nan"),
        "fees": float(sum(t.fees for t in trades)), "slip": float(sum(t.slip for t in trades)),
        "years": years,
    }


def placebo(h1: pd.DataFrame, gate: np.ndarray, n_trades: int, costs: Costs, runs: int, seed: int = 4) -> np.ndarray:
    """Mean net return per trade for random entries: same count, random eligible candles on (gated) days, 1.5 ATR stop, 23:00 exit."""
    rng = np.random.default_rng(seed)
    a14 = atr(h1[["open", "high", "low", "close"]], 14).to_numpy()
    c = h1["close"].to_numpy()
    hour = h1.index.hour.to_numpy()
    days = np.unique(h1.index.normalize().to_numpy())
    cand = np.flatnonzero((hour <= 19) & gate & ~np.isnan(a14))
    cand_days = h1.index.normalize()[cand]
    by_day = pd.Series(cand, index=cand_days).groupby(level=0).apply(lambda x: x.to_numpy())
    avail = by_day.index.to_numpy()
    out = np.empty(runs)
    for r in range(runs):
        pick = rng.choice(len(avail), size=min(n_trades, len(avail)), replace=False)
        sig = np.zeros(len(h1), bool)
        stop = np.full(len(h1), np.nan)
        for p in pick:
            i = rng.choice(by_day.iloc[p])
            sig[i], stop[i] = True, c[i] - 1.5 * a14[i]
        sim = simulate(h1, Signals(sig, stop, np.full(len(h1), np.nan), np.zeros(len(h1), bool)), costs, 100_000.0)
        out[r] = np.mean([t.ret for t in sim["trades"]]) if sim["trades"] else np.nan
    return out


# ---- verification ----------------------------------------------------------------------------------------------------------

def perturb_h1(h1: pd.DataFrame, cut: pd.Timestamp, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    out = h1.copy()
    later = out.index > cut
    base_px = h1.loc[h1.index <= cut, "close"].iloc[-1]
    ratio = pd.Series(np.exp(np.cumsum(rng.normal(0, 0.006, later.sum()))) * rng.uniform(0.6, 1.6), index=out.index[later])
    for col in ("open", "high", "low", "close"):
        out.loc[later, col] = h1.loc[later, col] / h1.loc[later, "close"] * base_px * ratio
    return out


def run_all(h1: pd.DataFrame, gates: dict[str, np.ndarray], costs: Costs, capital: float, leak: bool = False) -> dict[str, dict]:
    return {k: simulate(h1, build_signals(h1, k, gates.get(k)), costs, capital, leak) for k in "ABC"}


def make_gates(h1: pd.DataFrame, macro: pd.DataFrame, rules: dict) -> dict[str, np.ndarray]:
    daily = daily_from_hourly(h1)
    feat = build_features(daily, macro, rules)
    sma200 = daily["close"].rolling(200).mean()
    return {"B": day_gate(feat["regime_ok"].astype(bool), h1.index),
            "C": day_gate((daily["close"] > sma200), h1.index)}


def verify(h1: pd.DataFrame, macro: pd.DataFrame, rules: dict, gates: dict) -> tuple[list[str], bool]:
    lines, ok_all = [], True
    # 1. indicators causal: truncated vs full
    c = h1["close"]
    cut = h1.index[len(h1) // 2]
    trunc = h1[h1.index <= cut]
    same = all(np.isclose(f(c).loc[cut], f(trunc["close"]).loc[cut]) for f in (lambda s: ema(s, 20), lambda s: rsi(s, 14), lambda s: s.rolling(20).mean()))
    lines.append(f"- Indicators at a candle equal their value computed from candles up to it only: **{'PASS' if same else 'FAIL'}**.")
    ok_all &= same
    # 2. perturbation
    cuts = [pd.Timestamp(d) for d in ("2019-08-10 12:00", "2021-03-03 09:00", "2023-06-14 18:00", "2025-01-20 06:00")]
    bad = []
    for k, cutd in enumerate(cuts):
        pb = perturb_h1(h1, cutd, k)
        gb = make_gates(pb, macro, rules)
        a = run_all(h1, gates, COSTS["base"], 100_000.0)
        b = run_all(pb, gb, COSTS["base"], 100_000.0)
        for name in "ABC":
            ta = [(t.entry_time, t.exit_time, round(t.ret, 12)) for t in a[name]["trades"] if t.exit_time <= cutd]
            tb = [(t.entry_time, t.exit_time, round(t.ret, 12)) for t in b[name]["trades"] if t.exit_time <= cutd]
            if ta != tb:
                bad.append(f"{name}@{cutd}")
    lines.append(f"- Perturbation: after 4 random cut dates every later candle was replaced by different prices; the list of trades that exit by the "
                 f"cut (entry time, exit time, return) is identical for A, B and C: **{'PASS' if not bad else 'FAIL ' + str(bad)}**.")
    ok_all &= not bad
    # 3. leak detector
    correct = run_all(h1, gates, COSTS["base"], 100_000.0)
    leaked = run_all(h1, gates, COSTS["base"], 100_000.0, leak=True)
    pw = []
    for name in "ABC":
        mc = np.mean([t.ret for t in correct[name]["trades"]]) if correct[name]["trades"] else 0
        ml = np.mean([t.ret for t in leaked[name]["trades"]]) if leaked[name]["trades"] else 0
        pw.append((name, mc, ml))
    power = all(ml > mc + 0.001 for _, mc, ml in pw)
    lines.append("- Leak-direction check as pre-registered (acting on a candle's signal at that same candle's open), mean net return per trade, "
                 "correct vs leaked: " + ", ".join(f"{n} {mc:+.3%} vs {ml:+.3%}" for n, mc, ml in pw) +
                 f": {'passes' if power else '**does not pass for every strategy**'}. Non-gating after Amendment 1: for a mean-reversion entry, buying at the "
                 "signal candle's open is a worse price, so this check cannot show power for C.")
    # mutation test: a deliberately look-ahead strategy must be caught by the perturbation harness
    def mutant(frame, g, name):
        sg = build_signals(frame, name, g.get(name))
        cl = frame["close"].to_numpy()
        ahead = np.r_[cl[24:], np.full(24, np.nan)] > cl
        return Signals(sg.sig & ahead, sg.stop, sg.target, sg.ema_exit)

    mut_ok = []
    for name in "ABC":
        base_trades = simulate(h1, mutant(h1, gates, name), COSTS["base"], 100_000.0)["trades"]
        pool = [t for t in base_trades if t.entry_time >= START + pd.Timedelta(days=60)]
        picks = [pool[int(i)] for i in np.linspace(0, len(pool) - 1, 8)] if pool else []
        caught = 0
        for k, tr in enumerate(picks):
            cutd = tr.entry_time.normalize() + pd.Timedelta(days=1)       # midnight after a day the mutant traded
            pb = perturb_h1(h1, cutd, 100 + k)
            gb = make_gates(pb, macro, rules)
            ra = simulate(h1, mutant(h1, gates, name), COSTS["base"], 100_000.0)["trades"]
            rb = simulate(pb, mutant(pb, gb, name), COSTS["base"], 100_000.0)["trades"]
            ta = [(t.entry_time, t.exit_time, round(t.ret, 12)) for t in ra if t.exit_time <= cutd]
            tb = [(t.entry_time, t.exit_time, round(t.ret, 12)) for t in rb if t.exit_time <= cutd]
            caught += ta != tb
        mut_ok.append((name, caught))
    mut_pass = all(c >= 3 for _, c in mut_ok)
    lines.append("- Mutation test (Amendment 1): a deliberately look-ahead version of each strategy (needs the close 24 candles later to be higher) "
                 "was run through the same perturbation check at 8 cut dates (midnight after days on which the mutant traded); leak detected on " + ", ".join(f"{n} {c} of 8 cuts" for n, c in mut_ok) +
                 f": **{'PASS (harness can detect a leak)' if mut_pass else 'FAIL (harness has no power)'}**.")
    ok_all &= mut_pass
    # 4. gates use previous day only; 5. schedule rules
    daily = daily_from_hourly(h1)
    probe = pd.Series(False, index=daily.index)
    probe.iloc[len(probe) // 2] = True
    g = day_gate(probe, h1.index)
    first_on = h1.index[np.flatnonzero(g)[0]]
    gate_ok = first_on == daily.index[len(daily) // 2] + pd.Timedelta(days=1)
    lines.append(f"- Daily gates use the previous completed day only (a gate that is True only on day D first applies at {first_on.date()}, D+1): **{'PASS' if gate_ok else 'FAIL'}**.")
    ok_all &= gate_ok
    viol = 0
    for name in "ABC":
        sim = correct[name]
        per_day: dict = {}
        for t in sim["trades"]:
            per_day[t.entry_time.date()] = per_day.get(t.entry_time.date(), 0) + 1
            viol += (t.entry_time.hour > LAST_ENTRY_OPEN_HOUR) + (t.exit_time.date() != t.entry_time.date()) + (t.exit_time.hour > FORCE_EXIT_HOUR)
        viol += sum(v > 1 for v in per_day.values())
    lines.append(f"- Schedule: no entry after the 20:00 open, none held overnight, at most one entry a day (violations: {viol}): **{'PASS' if viol == 0 else 'FAIL'}**.")
    ok_all &= viol == 0
    return lines, ok_all


# ---- report ----------------------------------------------------------------------------------------------------------------

NAMES = {"A": "A. Opening-range breakout", "B": "B. Gated pullback-reclaim", "C": "C. Mean reversion"}


def build_report(placebo_runs: int = PLACEBO_RUNS) -> str:
    rules = load_rules()
    _, macro = load_data()
    h1 = pd.read_parquet(RAW_DIR / "btc_1h.parquet")
    h1 = h1[h1.index >= START - pd.Timedelta(days=400)]          # warm-up for the daily gates; trading starts at START
    gates = make_gates(h1, macro, rules)
    trade_mask = h1.index >= START

    freeze = json.loads((ROOT / "reports" / "intraday_freeze_2026-10-02.json").read_text(encoding="utf-8"))
    changed = [f for f, d in freeze["sha256"].items() if hashlib.sha256((ROOT / f).read_bytes()).hexdigest() != d]
    gaps = h1.index.to_series().diff().dt.total_seconds().div(3600)
    L = [f"# Intraday BTC study results ({date.today()})", "",
         f"Pre-registration: `intraday_preregistration_2026-10-02.md` (frozen {freeze['frozen_at_utc']}); frozen files unchanged: "
         f"**{'YES' if not changed else 'NO ' + str(changed)}**. Binance BTC/USDT 1h, {h1.index[trade_mask][0].date()} to "
         f"{h1.index[-1].date()} ({int(trade_mask.sum()):,} candles, {int((gaps > 1).sum())} gaps over 1 hour). Long-only spot, "
         "one entry per UTC day at most, flat before 23:00, no trade forced. A small set of 1h candles around 48 stop-out days had been "
         "downloaded earlier for a different purpose (stop slippage); no intraday strategy was run on them.", "",
         "## 1. Look-ahead verification (before results are read)", ""]
    vlines, vok = verify(h1[h1.index >= START - pd.Timedelta(days=400)].iloc[:], macro, rules, gates)
    L += vlines + ["", f"All-clear rule (perturbation passes and the mutation test shows the harness can detect a leak; see "
                   f"`intraday_preregistration_amendment_1_2026-10-02.md`): **{'YES' if vok else 'NO: results below must not be trusted'}**.", ""]

    H = h1
    sims = {sc: {cap: run_all(H, gates, COSTS[sc], cap) for cap in (100_000.0, 300.0)} for sc in COSTS}

    def sliced(res, lo=None, hi=None):
        eq = res["equity"][trade_mask[:len(res["equity"])]] if False else res["equity"][res["equity"].index >= START]
        tr = [t for t in res["trades"] if t.exit_time >= START]
        return tr, eq

    out = {}
    for k in "ABC":
        tr_b, eq_b = sliced(sims["base"][100_000.0][k])
        tr_h, _ = sliced(sims["harsh"][100_000.0][k])
        tr_3b, eq_3b = sliced(sims["base"][300.0][k])
        tr_3h, eq_3h = sliced(sims["harsh"][300.0][k])
        sb, sh = stats(tr_b, eq_b, 100_000.0), stats(tr_h, eq_b, 100_000.0)
        s3b, s3h = stats(tr_3b, eq_3b, 300.0), stats(tr_3h, eq_3h, 300.0)
        bs = week_bootstrap(tr_b)
        first = [t for t in tr_b if t.exit_time < HALF_SPLIT]
        second = [t for t in tr_b if t.exit_time >= HALF_SPLIT]
        yr = pd.Series([t.R for t in tr_b], index=[t.exit_time.year for t in tr_b]).groupby(level=0).mean()
        gate = gates.get(k, np.ones(len(H), bool))
        pl = placebo(H, gate & trade_mask, len(tr_b), COSTS["base"], placebo_runs, seed=ord(k))
        out[k] = dict(sb=sb, sh=sh, s3b=s3b, s3h=s3h, bs=bs, halves=(np.mean([t.R for t in first]) if first else np.nan,
                      np.mean([t.R for t in second]) if second else np.nan), yr=yr, pl=pl, skipped=sims["base"][300.0][k]["skipped"],
                      days_traded=len({t.entry_time.date() for t in tr_b}) / ((H.index[-1] - START).days), exits=pd.Series([t.reason for t in tr_b]).value_counts().to_dict(),
                      tin=float((eq_b != eq_b.shift()).mean()))

    L += ["## 2. Expectancy per trade (net of costs; large account so Binance's minimum never binds)", ""]
    rows = []
    for k in "ABC":
        r = out[k]
        sb, sh = r["sb"], r["sh"]
        rows.append([NAMES[k], sb["n"], f"{sb['per_year']:.0f}", f"{r['days_traded']:.0%}", f"{sb['win']:.0%}", pct(sb["gross"]), pct(-sb["cost"]),
                     pct(sb["ret"]), f"{sb['R']:+.3f}", f"{sb['medR']:+.2f}", f"{sb['pf']:.2f}", f"{r['bs']['lo']:+.3f}",
                     f"{sh['R']:+.3f}", f"{sb['margin']:.2f}x"])
    L += table(["Strategy", "Trades", "Per year", "Days traded", "Win rate", "Gross / trade", "Costs / trade", "Net / trade", "Mean net R",
                "Median R", "Profit factor", "Corrected lower bound (mean R)", "Harsh mean R", "Break-even cost / base cost"], rows)
    L += ["Exits: " + "; ".join(f"{NAMES[k][0]}: {out[k]['exits']}" for k in "ABC"), ""]

    L += ["## 3. Stability and drift", ""]
    rows = []
    for k in "ABC":
        r = out[k]
        pos_years = int((r["yr"] > 0).sum())
        rows.append([NAMES[k], f"{r['halves'][0]:+.3f} / {r['halves'][1]:+.3f}", f"{pos_years} of {len(r['yr'])}",
                     f"{np.nanmedian(r['pl']):+.3%} (95th pct {np.nanpercentile(r['pl'], 95):+.3%})", f"{r['sb']['ret']:+.3%}",
                     f"{np.mean(r['pl'] < r['sb']['ret']):.0%}"])
    L += table(["Strategy", "Mean R: before / after 2022-07-01", "Years with positive mean R", "Random-entry net / trade", "Strategy net / trade",
                "Share of random runs beaten"], rows)
    L += ["Calendar-year mean net R (2018 and 2026 partial):", ""]
    years = sorted(set().union(*[set(out[k]["yr"].index) for k in "ABC"]))
    L += table(["Year"] + [NAMES[k] for k in "ABC"], [[y] + [f"{out[k]['yr'][y]:+.3f}" if y in out[k]["yr"].index else "no trades" for k in "ABC"] for y in years])

    L += ["## 4. The $300 account (1% risk, capped at 98% of cash)", ""]
    rows = []
    for k in "ABC":
        r = out[k]
        for sc, s in (("base", r["s3b"]), ("harsh", r["s3h"])):
            rows.append([NAMES[k], sc, f"{s['final']:,.2f}", pct(s["cagr"]), pct(s["dd"]), f"{s['profit_py']:+.2f}", f"{s['sharpe']:.2f}",
                         f"{s['fees']:.2f} / {s['slip']:.2f}", s["streak"], r["skipped"] if sc == "base" else ""])
    L += table(["Strategy", "Fills", "Final capital", "CAGR", "Max DD", "Profit per year ($)", "Sharpe", "Fees / slippage ($)", "Longest losing streak", "Skipped (minimum order)"], rows)

    # gates
    L += ["## 5. Pre-registered gates", ""]
    labels, rows = {}, []
    for k in "ABC":
        r = out[k]
        sb, sh = r["sb"], r["sh"]
        g = {
            "N1 >= 300 trades": (sb["n"] >= MIN_TRADES, f"{sb['n']}"),
            "N2 corrected lower bound > 0": (r["bs"]["lo"] > 0, f"{r['bs']['lo']:+.3f} (p = {r['bs']['p']:.3f})"),
            "N3 harsh R > 0 and break-even >= 1.5x": (sh["R"] > 0 and sb["margin"] >= COST_MARGIN_MIN, f"{sh['R']:+.3f}, {sb['margin']:.2f}x"),
            "N4 both halves > 0 and >= 6 of 9 years": (all(h > 0 for h in r["halves"]) and int((r["yr"] > 0).sum()) >= YEARS_POSITIVE_MIN,
                                                      f"{r['halves'][0]:+.3f}/{r['halves'][1]:+.3f}, {int((r['yr'] > 0).sum())} yrs"),
            "N5 beats 95th pct of random entries": (sb["ret"] > np.nanpercentile(r["pl"], 100 * PLACEBO_PCTL), f"{sb['ret']:+.3%} vs {np.nanpercentile(r['pl'], 95):+.3%}"),
            "N6 CAGR >= 5%, DD <= 15%, harsh profitable": (r["s3b"]["cagr"] >= CAGR_MIN and r["s3b"]["dd"] >= -DD_MAX and r["s3h"]["cagr"] > 0,
                                                          f"{r['s3b']['cagr']:+.1%}, {r['s3b']['dd']:.1%}, harsh {r['s3h']['cagr']:+.1%}"),
        }
        if not g["N1 >= 300 trades"][0] or not g["N2 corrected lower bound > 0"][0] or not g["N3 harsh R > 0 and break-even >= 1.5x"][0]:
            lab = "NO EDGE"
        elif not (g["N4 both halves > 0 and >= 6 of 9 years"][0] and g["N5 beats 95th pct of random entries"][0]):
            lab = "NOT ROBUST"
        elif not g["N6 CAGR >= 5%, DD <= 15%, harsh profitable"][0]:
            lab = "WEAK"
        else:
            lab = "WORTH FORWARD-TESTING"
        labels[k] = (lab, g)
    for gate in labels["A"][1]:
        rows.append([gate] + [("PASS " if labels[k][1][gate][0] else "**FAIL** ") + labels[k][1][gate][1] for k in "ABC"])
    rows.append(["**Outcome**"] + [f"**{labels[k][0]}**" for k in "ABC"])
    L += table(["Gate"] + [NAMES[k] for k in "ABC"], rows)

    L += ["Note on N5: it asks whether a strategy beats random entries, not whether it is profitable. A passes it by being *less negative* than "
          "random entries (-0.18% vs -0.19% per trade); that is not an edge. Break-even cost / base cost below 1x means costs would have to fall "
          "below the quoted fraction of what they are for the strategy to merely break even (A: about 0.13% round trip, against a 0.20% "
          "fee alone at Binance's standard rate and about 0.15% with the BNB discount, before any slippage).", ""]
    L += ["## 6. Verdict", ""]
    for k in "ABC":
        L.append(f"- **{NAMES[k]}: {labels[k][0]}.** Mean net R {out[k]['sb']['R']:+.3f} per trade (gross move {out[k]['sb']['gross']:+.3%}, "
                 f"costs {out[k]['sb']['cost']:.3%} per trade).")
    good = [k for k in "ABC" if labels[k][0] == "WORTH FORWARD-TESTING"]
    L += ["", "Positive expectancy after realistic costs demonstrated: " + (", ".join(NAMES[k] for k in good) if good else "**none**") + ".",
          "Three strategies were tested, so significance was corrected for three; no parameter was changed after the first run."]
    return "\n".join(L)


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Pre-registered intraday BTC study")
    ap.add_argument("--placebo-runs", type=int, default=PLACEBO_RUNS)
    args = ap.parse_args()
    text = build_report(args.placebo_runs)
    REPORTS_DIR.mkdir(exist_ok=True)
    path = REPORTS_DIR / f"intraday_{date.today()}.md"
    path.write_text(text, encoding="utf-8")
    print(f"Saved to {path} ({len(text.splitlines())} lines)")


if __name__ == "__main__":
    main()
