"""Profitability audit (v3 gate): is the strategy economically viable after realistic costs?

Nothing here tunes parameters. Every table either measures the current rules under stricter assumptions, or checks
whether the result could be luck (placebo entries, parameter neighbours, other assets, Monte Carlo).
Run: uv run python -m spot_trd.audit
"""
import copy
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from spot_trd import research
from spot_trd.backtest import Result, run_backtest
from spot_trd.config import RAW_DIR, REPORTS_DIR, load_rules, load_universe
from spot_trd.data import fetch_ohlcv, load_data
from spot_trd.regime import build_features
from spot_trd.report import fmt_pct, max_drawdown, summarize

SPLIT = pd.Timestamp("2023-01-01")       # development 2018-03..2022, out-of-sample 2023-01..now
CAPITALS = (25.0, 50.0, 100.0, 250.0, 300.0)
EDGE_CAPITAL, EDGE_RISK = 100_000.0, 0.02  # large account: Binance's minimum order never binds, so this measures the signal
STOP_KINDS = ("stop", "trail", "breakeven")


# ---------------------------------------------------------------- execution scenarios

def variant(base: dict, pen: float, next_open: bool, exit_slip: float, stop_slip: float, fee: float | None = None,
            stop_fill: float | None = None) -> dict:
    """stop_slip is what position sizing assumes; stop_fill (if given) is what stops actually suffer."""
    r = copy.deepcopy(base)
    r["execution"] = {"limit_penetration": pen, "exit_at_next_open": next_open, "exit_slippage": exit_slip,
                      "stop_fill_slippage": stop_fill}
    r["exit"]["stop_slippage"] = stop_slip
    if fee is not None:
        r["market"]["fee_rate"] = fee
    return r


def ladder(base: dict) -> list[tuple[str, dict]]:
    """Cumulative path from the published v2 assumptions to a harsh-but-plausible fill model."""
    return [
        ("0. v2 as first published (touch = fill, regime exit at same close, 0.1% stop slip)",
         variant(base, 0.0, False, 0.0, 0.001)),
        ("1. + exits fill at the NEXT open with 0.1% slippage", variant(base, 0.0, True, 0.001, 0.001)),
        ("2. + limit buys need a 0.05% trade-through = **base (rules.yaml)**", variant(base, 0.0005, True, 0.001, 0.001)),
        ("3. + stop slippage 0.3%", variant(base, 0.0005, True, 0.001, 0.003)),
        ("4. **harsh**: 0.15% trade-through, 0.3% exit slip, 0.5% stop slip", variant(base, 0.0015, True, 0.003, 0.005)),
        ("5. **gap stress**: base, but stops fill 1.5% worse than the position was sized for",
         variant(base, 0.0005, True, 0.001, 0.001, stop_fill=0.015)),
    ]


# ---------------------------------------------------------------- metrics

def longest_streak(flags: list[bool]) -> int:
    best = cur = 0
    for f in flags:
        cur = cur + 1 if f else 0
        best = max(best, cur)
    return best


def monthly_profit(eq: pd.Series, initial: float) -> pd.Series:
    m = eq.resample("ME").last()
    return m.diff().fillna(m.iloc[0] - initial)


def sharpe(eq: pd.Series) -> float:
    r = eq.pct_change().dropna()
    return float(np.sqrt(365) * r.mean() / r.std()) if r.std() > 0 else float("nan")


def economics(res: Result, lo: pd.Timestamp | None = None, hi: pd.Timestamp | None = None) -> dict:
    """Everything the profitability question needs, in dollars as well as percentages."""
    eq = res.equity
    mask = pd.Series(True, index=eq.index)
    if lo is not None:
        mask &= eq.index >= lo
    if hi is not None:
        mask &= eq.index < hi
    eq = eq[mask]
    ts = [t for t in res.trades if (lo is None or t.exit_date >= lo) and (hi is None or t.exit_date < hi)]
    start = res.initial if lo is None else float(eq.iloc[0])
    years = (eq.index[-1] - eq.index[0]).days / 365.25
    final = float(eq.iloc[-1])
    pnl = np.array([t.pnl for t in ts])
    r = np.array([t.r_multiple for t in ts])
    gains, losses = pnl[pnl > 0].sum(), -pnl[pnl < 0].sum()
    mp = monthly_profit(eq, start)
    in_mkt = res.in_market[mask]
    expo = res.exposure[mask]
    days = len(eq)
    return {
        "start": start, "final": final, "years": years,
        "total_return": final / start - 1,
        "cagr": (final / start) ** (1 / years) - 1 if years > 0 and final > 0 else float("nan"),
        "profit": final - start,
        "profit_per_year": (final - start) / years if years > 0 else float("nan"),
        "avg_month": float(mp.mean()), "median_month": float(mp.median()), "months": len(mp),
        "months_up": int((mp > 0.005).sum()), "months_down": int((mp < -0.005).sum()),
        "worst_R": float(r.min()) if len(r) else float("nan"),
        "trades": len(ts), "trades_per_month": len(ts) / (years * 12) if years > 0 else float("nan"),
        "win_rate": float((pnl > 0).mean()) if len(pnl) else float("nan"),
        "avg_R": float(r.mean()) if len(r) else float("nan"),
        "profit_factor": float(gains / losses) if losses > 0 else float("inf"),
        "max_dd": float(max_drawdown(eq)),
        "losing_streak": longest_streak([p < 0 for p in pnl]),
        "fees": float(sum(t.fees for t in ts)) + (res.extra_fees if lo is None and hi is None else 0.0),
        "slippage": float(sum(t.slippage for t in ts)) + (res.extra_slippage if lo is None and hi is None else 0.0),
        "utilization": float(expo.mean()), "utilization_in_mkt": float(expo[in_mkt].mean()) if in_mkt.any() else 0.0,
        "time_in_mkt": float(in_mkt.mean()),
        "no_trade_days": 1 - len([d for d in res.trade_days if d in eq.index]) / days,
        "sharpe": sharpe(eq),
        "pnl": pnl, "R": r,
    }


# ---------------------------------------------------------------- baselines (same costs, all-in, next-open execution)

@dataclass
class Hold:
    equity: pd.Series
    pnl: list
    trades: int
    fees: float


def hold_strategy(feat: pd.DataFrame, target: pd.Series, capital: float, fee: float, slip: float) -> Hold:
    """Hold BTC whenever `target` (decided at the previous close) is True, else USDT. Fills at the open +/- slippage."""
    o, c = feat["open"].to_numpy(), feat["close"].to_numpy()
    tgt = target.to_numpy()
    cash, qty, basis, fees = capital, 0.0, 0.0, 0.0
    eq, pnl, n = [], [], 0
    for i in range(len(feat)):
        want = bool(tgt[i - 1]) if i > 0 else False
        if want and qty == 0:
            px = o[i] * (1 + slip)
            qty = cash / (px * (1 + fee))
            fees += qty * px * fee
            basis, cash = cash, 0.0
        elif not want and qty > 0:
            px = o[i] * (1 - slip)
            cash = qty * px * (1 - fee)
            fees += qty * px * fee
            pnl.append(cash - basis)
            qty, n = 0.0, n + 1
        eq.append(cash + qty * c[i])
    if qty > 0:
        pnl.append(eq[-1] - basis)  # mark the open position so win rate / PF include it
    return Hold(pd.Series(eq, index=feat.index), pnl, n + (1 if qty > 0 else 0), fees)


def scale_to_drawdown(eq: pd.Series, target_dd: float) -> tuple[pd.Series, float]:
    """Hold only a fraction w of a baseline (rest in USDT, no leverage) so its max drawdown equals target_dd."""
    ret = eq.pct_change().fillna(0.0)

    def curve(w: float) -> pd.Series:
        return (1 + w * ret).cumprod() * eq.iloc[0]

    if abs(max_drawdown(eq)) <= abs(target_dd):
        return eq, 1.0
    lo, hi = 0.0, 1.0
    for _ in range(40):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if abs(max_drawdown(curve(mid))) <= abs(target_dd) else (lo, mid)
    return curve(lo), lo


def base_stats(eq: pd.Series) -> dict:
    years = (eq.index[-1] - eq.index[0]).days / 365.25
    tot = eq.iloc[-1] / eq.iloc[0] - 1
    dd = max_drawdown(eq)
    cagr = (1 + tot) ** (1 / years) - 1
    return {"total": tot, "cagr": cagr, "dd": dd, "calmar": cagr / abs(dd) if dd < 0 else float("nan"), "sharpe": sharpe(eq)}


# ---------------------------------------------------------------- statistics

def bootstrap_mean(x: np.ndarray, n: int = 10_000, seed: int = 7) -> tuple[float, float, float]:
    """(2.5%, 97.5%, P(mean <= 0)) of the mean of x under resampling."""
    if len(x) < 3:
        return float("nan"), float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    means = rng.choice(x, size=(n, len(x))).mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5)), float((means <= 0).mean())


def monte_carlo(fracs: np.ndarray, per_year: float, years: float, capital: float, n: int = 20_000, seed: int = 11,
                block: int = 1, shift: float = 0.0) -> dict:
    """Resample per-trade returns (fraction of equity at entry). shift removes part of the mean (0.5 = half the edge)."""
    rng = np.random.default_rng(seed)
    fr = fracs - shift * fracs.mean()
    finals, dds, streaks = np.empty(n), np.empty(n), np.empty(n)
    counts = rng.poisson(per_year * years, size=n)
    for s in range(n):
        k = max(int(counts[s]), 1)
        if block > 1:
            starts = rng.integers(0, len(fr), size=(k // block) + 1)
            seq = np.concatenate([np.take(fr, range(st, st + block), mode="wrap") for st in starts])[:k]
        else:
            seq = rng.choice(fr, size=k)
        path = np.concatenate([[1.0], np.cumprod(1 + seq)])
        finals[s] = path[-1]
        dds[s] = (path / np.maximum.accumulate(path) - 1).min()
        streaks[s] = longest_streak(list(seq < 0))
    return {
        "capital": capital, "years": years,
        "p5": np.percentile(finals, 5) * capital, "p25": np.percentile(finals, 25) * capital,
        "p50": np.percentile(finals, 50) * capital, "p75": np.percentile(finals, 75) * capital,
        "p95": np.percentile(finals, 95) * capital,
        "p_loss": float((finals < 1).mean()), "p_lose10": float((finals < 0.9).mean()),
        "dd_median": float(np.median(dds)), "dd_p95": float(np.percentile(dds, 5)),
        "p_dd10": float((dds <= -0.10).mean()), "p_dd20": float((dds <= -0.20).mean()),
        "streak_median": float(np.median(streaks)), "streak_p95": float(np.percentile(streaks, 95)),
    }


# ---------------------------------------------------------------- data for other assets

def load_asset(symbol: str, refresh: bool = False) -> pd.DataFrame:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"{symbol.replace('/', '_')}_1d.parquet"
    if refresh or not path.exists():
        fetch_ohlcv(symbol).to_parquet(path)
    return pd.read_parquet(path)


# ---------------------------------------------------------------- audit checks

def lookahead_test(btc: pd.DataFrame, macro: pd.DataFrame, rules: dict, feat: pd.DataFrame, step: int = 37) -> tuple[int, dict]:
    """Rebuild every feature from data truncated at date T; any difference from the full-data value is look-ahead."""
    num = ["ema_pb", "ema_fast", "ema_slow", "rsi", "atr"]
    flags = ["monthly_up", "daily_up", "trend_ok", "risk_off", "regime_ok", "pullback", "signal"]
    bad: dict[str, list[str]] = {}
    dates = feat.index[::step]
    for d in dates:
        sub = build_features(btc[btc.index <= d], macro[macro.index <= d], rules)
        if d not in sub.index:
            continue
        for c in num + flags:
            same = np.isclose(sub.loc[d, c], feat.loc[d, c], rtol=1e-9) if c in num else sub.loc[d, c] == feat.loc[d, c]
            if not same:
                bad.setdefault(c, []).append(str(d.date()))
    return len(dates), bad


def stop_overshoot(res: Result, feat: pd.DataFrame, offset: float) -> dict:
    """How far below the stop did the day's low trade on days a stop-type exit happened?"""
    over = []
    for t in res.trades:
        if t.exit_reason in STOP_KINDS and t.exit_date in feat.index and t.stop_level > 0:
            over.append(max(t.stop_level - feat.loc[t.exit_date, "low"], 0.0) / t.stop_level)
    over = np.array(over)
    return {
        "n": len(over), "median": float(np.median(over)), "mean": float(over.mean()), "p90": float(np.percentile(over, 90)),
        "max": float(over.max()), "share_beyond_limit": float((over > offset).mean()),
    }


def ablation(feat: pd.DataFrame, monthly: bool, daily: bool, macro: bool, pullback: bool) -> pd.DataFrame:
    """Switch individual rule components on/off to see which ones carry the result."""
    f = feat.copy()
    f["trend_ok"] = (f["monthly_up"] if monthly else True) & (f["daily_up"] if daily else True)
    f["regime_ok"] = f["trend_ok"] & (~f["risk_off"] if macro else True)
    f["signal"] = f["regime_ok"] & (f["pullback"] if pullback else True)
    return f


def placebo(feat: pd.DataFrame, rules: dict, universe: dict, n: int = 300, seed: int = 5) -> dict:
    """Same gate, exits and sizing, but entry days drawn at random with the real signal's frequency inside the gate."""
    rng = np.random.default_rng(seed)
    gate = feat["regime_ok"].to_numpy()
    p = feat["signal"].sum() / max(gate.sum(), 1)
    rets, rr, avgr = [], [], []
    for _ in range(n):
        f = feat.copy()
        f["signal"] = gate & (rng.random(len(f)) < p)
        res = run_backtest(f, rules, universe, EDGE_CAPITAL, EDGE_RISK)
        s = summarize(res.trades, res.equity, res.initial)
        rets.append(s["total_return"])
        rr.append(s["total_return"] / max(abs(s["max_drawdown"]), 0.01))
        avgr.append(s["avg_R"])
    return {"ret": np.array(rets), "ret_dd": np.array(rr), "avg_r": np.array(avgr), "p": p}


def hourly_bars(days: list[pd.Timestamp]) -> pd.DataFrame:
    """1-hour BTC/USDT candles for the given UTC days (cached), to see what happens inside a stop-out day."""
    from spot_trd.data import _exchange, retry

    path = RAW_DIR / "btc_1h_stopdays.parquet"
    have = pd.read_parquet(path) if path.exists() else pd.DataFrame()
    have_days = set(have.index.normalize().unique()) if len(have) else set()
    ex, rows = _exchange(), []
    for d in days:
        if d.normalize() in have_days:
            continue
        for r in retry(lambda: ex.fetch_ohlcv("BTC/USDT", "1h", since=int(d.timestamp() * 1000), limit=24)):
            rows.append([pd.to_datetime(r[0], unit="ms")] + r[1:5])
    if rows:
        new = pd.DataFrame(rows, columns=["t", "open", "high", "low", "close"]).set_index("t")
        have = pd.concat([have, new]).sort_index()
        have = have[~have.index.duplicated()]
        have.to_parquet(path)
    return have


def intraday_stop_report(res: Result, offset: float) -> list[str]:
    """For each stop-type exit: inside the first hour that traded through the stop, how far below it did price go, and
    where did the hour close? (Hourly candles can't show the exact fill, but they bound it far better than daily ones.)"""
    stops = [t for t in res.trades if t.exit_reason in STOP_KINDS and t.stop_level > 0]
    hours = hourly_bars([t.exit_date for t in stops])
    deep, close_below = [], []
    for t in stops:
        day = hours[(hours.index >= t.exit_date) & (hours.index < t.exit_date + pd.Timedelta(days=1))]
        hit = day[day["low"] <= t.stop_level]
        if hit.empty:
            continue
        first = hit.iloc[0]
        deep.append(max(t.stop_level - first["low"], 0.0) / t.stop_level)
        close_below.append(first["close"] < t.stop_level * (1 - offset))
    g = np.array(deep)
    if not len(g):
        return []
    return [f"**Hourly check ({len(g)} stop-type exits).** Within the first hour that traded through the stop, the hour's low was "
            f"below the stop by a median {np.median(g):.2%} (mean {g.mean():.2%}, 90th percentile {np.percentile(g, 90):.2%}, "
            f"worst {g.max():.2%}). In {int((g > offset).sum())} of {len(g)} cases price dropped more than the stop-limit's "
            f"{offset:.1%} band inside that single hour, and in {int(sum(close_below))} the hour even closed below the limit "
            "price: those are the cases where a stop-limit could rest unfilled. Candles can't show the exact fill; treat "
            "0.1% as the typical case and the 0.5% and 1.5% rows as the tail.", ""]


# ---------------------------------------------------------------- report helpers

def usd(x: float) -> str:
    return f"{x:+,.2f}"


def pct(x: float, signed: bool = True) -> str:
    return "n/a" if pd.isna(x) else (f"{x:+.1%}" if signed else f"{x:.1%}")


def table(header: list[str], rows: list[list]) -> list[str]:
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return out + [""]


def econ_table(cols: dict[str, dict]) -> list[str]:
    names = list(cols)
    spec = [
        ("Capital at start -> end ($)", lambda e: f"{e['start']:,.2f} -> {e['final']:,.2f}"),
        ("Total return", lambda e: pct(e["total_return"])),
        ("Annualized return (CAGR)", lambda e: pct(e["cagr"])),
        ("Profit per year ($, simple average)", lambda e: usd(e["profit_per_year"])),
        ("Average monthly profit ($)", lambda e: usd(e["avg_month"])),
        ("Median monthly profit ($)", lambda e: usd(e["median_month"])),
        ("Months up / flat / down", lambda e: f"{e['months_up']} / {e['months'] - e['months_up'] - e['months_down']} / {e['months_down']}"),
        ("Trades (total / per month)", lambda e: f"{e['trades']} / {e['trades_per_month']:.2f}"),
        ("Win rate", lambda e: pct(e["win_rate"], False)),
        ("Average R", lambda e: f"{e['avg_R']:+.2f}"),
        ("Profit factor", lambda e: f"{e['profit_factor']:.2f}"),
        ("Max drawdown", lambda e: pct(e["max_dd"])),
        ("Longest losing streak (trades)", lambda e: str(e["losing_streak"])),
        ("Worst single trade (R)", lambda e: f"{e['worst_R']:+.2f}"),
        ("Fees paid ($ total / per year)", lambda e: f"{e['fees']:.2f} / {e['fees'] / e['years']:.2f}"),
        ("Estimated slippage ($ total)", lambda e: f"{e['slippage']:.2f}"),
        ("Capital utilization (avg, all days / when in a trade)",
         lambda e: f"{e['utilization']:.1%} / {e['utilization_in_mkt']:.1%}"),
        ("Time in a position", lambda e: f"{e['time_in_mkt']:.1%}"),
        ("Days with no trade", lambda e: f"{e['no_trade_days']:.1%}"),
    ]
    return table(["Metric"] + names, [[label] + [fn(cols[n]) for n in names] for label, fn in spec])


def summary_block(cap: float, e: dict) -> str:
    return (f"Starting capital: ${cap:,.0f} | est. profit/year: ${e['profit_per_year']:+.2f} | est. profit/month: "
            f"${e['avg_month']:+.2f} | max drawdown: {e['max_dd']:.1%} | trades/year: {e['trades'] / e['years']:.1f} | "
            f"fees/year: ${e['fees'] / e['years']:.2f}")


# ---------------------------------------------------------------- the report

def build_report(refresh: bool = False, placebo_runs: int = 300) -> str:
    base, universe = load_rules(), load_universe()
    btc, macro = load_data(refresh)
    feat = build_features(btc, macro, base)
    bh = feat["close"]
    L: list[str] = [f"# Profitability audit, rules v{base['version']} ({date.today()})", "",
                    f"Data: BTC/USDT daily, {feat.index[0].date()} to {feat.index[-1].date()} "
                    f"({len(feat)} bars). Development = before {SPLIT.date()}, out-of-sample = {SPLIT.date()} onward.", ""]

    # 1. integrity -----------------------------------------------------------------------------------------------
    gaps = btc.index.to_series().diff().dt.days
    n_dates, bad = lookahead_test(btc, macro, base, feat)
    L += ["## 1. Code and data audit", "",
          f"- BTC bars: {len(btc)}, duplicates {int(btc.index.duplicated().sum())}, missing days {int((gaps > 1).sum())}, "
          f"non-positive prices {int((btc[['open', 'high', 'low', 'close']] <= 0).sum().sum())}.",
          f"- Macro series missing share: {', '.join(f'{k} {v:.1%}' for k, v in macro.isna().mean().items())}; "
          f"oil printed {macro['oil'].min():.2f} (Apr 2020), clipped in the code.",
          f"- **Look-ahead test:** features rebuilt from data truncated at {n_dates} different dates; mismatches vs the "
          f"full-data values: {bad or 'none'}.",
          f"- Gate frequency: trend gate open {feat['trend_ok'].mean():.0%} of days, macro risk-off "
          f"{feat['risk_off'].mean():.0%}, entry signal {feat['signal'].mean():.1%}.", ""]

    # 2. assumption ladder ---------------------------------------------------------------------------------------
    L += ["## 2. Execution realism: what each assumption was worth", "",
          "Cumulative changes to the fill model. `Edge` = 100,000 USDT at 2% risk (signal quality without Binance's "
          "5 USDT minimum); `$25` = the real account and risk schedule.", ""]
    rows, runs = [], {}
    for name, r in ladder(base):
        e = economics(run_backtest(feat, r, universe, EDGE_CAPITAL, EDGE_RISK))
        small_res = run_backtest(feat, r, universe, 25.0)
        s = economics(small_res)
        runs[name] = (r, small_res)
        rows.append([name, e["trades"], pct(e["total_return"]), pct(e["max_dd"]), f"{e['avg_R']:+.2f}", f"{e['profit_factor']:.2f}", f"{e['worst_R']:+.2f}",
                     f"{s['final']:.2f}", pct(s["total_return"]), s["trades"]])
    L += table(["Fill model", "Edge trades", "Edge return", "Edge max DD", "Edge avg R", "Edge PF", "Edge worst trade (R)",
                "$25 final", "$25 return", "$25 trades"], rows)

    base_res_edge = run_backtest(feat, base, universe, EDGE_CAPITAL, EDGE_RISK)
    ov = stop_overshoot(base_res_edge, feat, base["exit"]["stop_limit_offset"])
    L += [f"Stop realism: on the {ov['n']} days a stop-type exit happened, the day's low traded below the stop by a median "
          f"{ov['median']:.2%} (mean {ov['mean']:.2%}, 90th percentile {ov['p90']:.2%}, worst {ov['max']:.2%}). "
          f"{ov['share_beyond_limit']:.0%} of those days pierced the stop-limit's 0.5% limit price, where a stop-LIMIT "
          f"sell may not fill at all (the backtest assumes it does; {base_res_edge.stop_blowthroughs} blow-throughs counted). "
          "The low is a bound, not the fill price, so 0.1-0.5% stop slippage brackets the evidence.", ""]
    L += intraday_stop_report(base_res_edge, base["exit"]["stop_limit_offset"])

    # 3. out of sample + walk forward ---------------------------------------------------------------------------
    L += ["## 3. Out-of-sample and walk-forward", ""]
    full_edge = economics(base_res_edge)
    dev, oos = economics(base_res_edge, None, SPLIT), economics(base_res_edge, SPLIT, None)
    lo, hi, p0 = bootstrap_mean(full_edge["R"])
    L += ["Fixed v2 rules at edge capital (nothing tuned in this section):", ""]
    L += table(["Period", "Trades", "Win rate", "Avg R", "Profit factor", "Return", "Max DD", "BTC buy&hold", "BTC max DD"],
               [[name, e["trades"], pct(e["win_rate"], False), f"{e['avg_R']:+.2f}", f"{e['profit_factor']:.2f}",
                 pct(e["total_return"]), pct(e["max_dd"]),
                 pct(bh[(bh.index >= (a or bh.index[0])) & (bh.index < (b or bh.index[-1] + pd.Timedelta(days=1)))].iloc[-1]
                     / bh[(bh.index >= (a or bh.index[0])) & (bh.index < (b or bh.index[-1] + pd.Timedelta(days=1)))].iloc[0] - 1),
                 pct(max_drawdown(bh[(bh.index >= (a or bh.index[0])) & (bh.index < (b or bh.index[-1] + pd.Timedelta(days=1)))]))]
                for name, e, a, b in (("Development 2018-2022", dev, None, SPLIT), ("Out-of-sample 2023-now", oos, SPLIT, None),
                                      ("Full period", full_edge, None, None))])
    for name, e in (("development", dev), ("out-of-sample", oos), ("full", full_edge)):
        l, h, p = bootstrap_mean(e["R"])
        L.append(f"- Bootstrap 95% interval for mean R, {name}: [{l:+.2f}, {h:+.2f}] over {e['trades']} trades; "
                 f"P(true mean R <= 0) ~ {p:.1%}.")
    L.append("")

    # honest note on contamination
    L += ["**Contamination warning.** v1 (fixed targets) was tested on the whole 2018-now history and failed; v2's exit "
          "design came after seeing that. The 2023+ block was then used again to confirm v2 and to reject the upgrade "
          "ideas. It is therefore *not* a clean holdout. Treat it as a consistency check; the only untouched data is "
          "other assets (see the universe study) and the live paper-trading that started 2026-10-01. Roughly 30 rule "
          "variants (21 research, 6 upgrade tests, plus the hand-built v1 and earlier design choices) have been judged "
          "on this same history, so a nominal p-value of 2% for the whole-period mean R is not credible as stated "
          "(a crude Bonferroni correction for 30 looks puts it near 60%).", ""]

    # walk-forward with annual re-selection
    cands = research.candidates(base)
    v1 = copy.deepcopy(base)
    v1["exit"].update(tp1_r=1.5, tp2_r=3.0, tp1_fraction=0.5, trail_atr_mult=None, regime_exit=False, max_hold_days=10)
    cands = [("v1 fixed targets (TP 1.5R/3R, 10-day limit, no trend exit)", v1)] + cands
    cruns = []
    for name, r in cands:
        f = build_features(btc, macro, r)
        cruns.append((name, run_backtest(f, r, universe, EDGE_CAPITAL, EDGE_RISK)))
    fixed_name = "pullback stop 1.0 ATR, trail 2.0 ATR, TP1 off"
    wf_rows, daily_parts = [], []
    for year in range(2021, feat.index[-1].year + 1):
        cut, end = pd.Timestamp(f"{year}-01-01"), pd.Timestamp(f"{year + 1}-01-01")
        best, best_score = None, float("-inf")
        for name, res in cruns:
            eq = res.equity[res.equity.index < cut]
            ts = [t for t in res.trades if t.exit_date < cut]
            sc = research.score(summarize(ts, eq, eq.iloc[0]))
            if sc > best_score:
                best, best_score = (name, res), sc

        def year_ret(res):
            eq = res.equity
            prev = eq[eq.index < cut].iloc[-1]
            cur = eq[eq.index < end].iloc[-1]
            return cur / prev - 1

        fixed = next(r for n, r in cruns if n == fixed_name)
        btc_ret = bh[bh.index < end].iloc[-1] / bh[bh.index < cut].iloc[-1] - 1
        if best is None:
            wf_rows.append([year, "(none eligible: stay in USDT)", pct(0.0), pct(year_ret(fixed)), pct(btc_ret)])
            daily_parts.append(pd.Series(0.0, index=feat.index[(feat.index >= cut) & (feat.index < end)]))
        else:
            wf_rows.append([year, best[0], pct(year_ret(best[1])), pct(year_ret(fixed)), pct(btc_ret)])
            eq = best[1].equity
            daily_parts.append(eq.pct_change().loc[(eq.index >= cut) & (eq.index < end)])
    stitched = (1 + pd.concat(daily_parts).fillna(0)).cumprod()
    L += ["Walk-forward: each January, pick the best of the 21 research variants using ONLY earlier data (same rule as "
          "`spot research`), trade it for that year, repeat.", ""]
    L += table(["Test year", "Variant chosen from prior data", "Walk-forward return", "Fixed v2 return", "BTC buy&hold"], wf_rows)
    wf = base_stats(stitched)
    fx = base_stats(next(r for n, r in cruns if n == fixed_name).equity[lambda s: s.index >= pd.Timestamp("2021-01-01")])
    L += [f"Stitched walk-forward 2021-now: total {pct(wf['total'])}, CAGR {pct(wf['cagr'])}, max DD {pct(wf['dd'])}. "
          f"Fixed v2 over the same years: total {pct(fx['total'])}, max DD {pct(fx['dd'])}.", ""]

    # by calendar year / regime
    L += ["Fixed v2 by calendar year (BTC market regime shown by its own return):", ""]
    yr_rows = []
    for year in sorted(set(feat.index.year)):
        e = feat.index.year == year
        c = bh[e]
        prev_close = bh[bh.index < c.index[0]]
        btc_r = c.iloc[-1] / (prev_close.iloc[-1] if len(prev_close) else c.iloc[0]) - 1
        eq = base_res_edge.equity[base_res_edge.equity.index.year == year]
        prev = base_res_edge.equity[base_res_edge.equity.index < eq.index[0]]
        sr = eq.iloc[-1] / (prev.iloc[-1] if len(prev) else EDGE_CAPITAL) - 1
        ts = [t for t in base_res_edge.trades if t.exit_date.year == year]
        yr_rows.append([year, "bull" if btc_r > 0.3 else "bear" if btc_r < -0.2 else "range", pct(btc_r), pct(sr), len(ts),
                        f"{sum(t.r_multiple for t in ts):+.1f}", f"{base_res_edge.exposure[base_res_edge.exposure.index.year == year].mean():.0%}"])
    L += table(["Year", "BTC regime", "BTC", "Strategy (edge)", "Trades", "Sum R", "Avg exposure"], yr_rows)

    # 4. baselines ----------------------------------------------------------------------------------------------
    L += ["## 4. Does the complexity add value? Same period, same costs", ""]
    fee, slip = base["market"]["fee_rate"], base["exit"]["stop_slippage"]
    start25 = 25.0
    s25 = run_backtest(feat, base, universe, start25)
    e25 = economics(s25)
    sma200 = feat["close"].rolling(200).mean()
    targets = {
        "BTC buy & hold": pd.Series(True, index=feat.index),
        "Simple trend: BTC above its 200-day SMA, else USDT": feat["close"] > sma200,
        "Strategy's own gate held all-in (1M+1D trend, macro calm)": feat["regime_ok"],
    }
    rows = [["Stay in USDT", pct(0.0), pct(0.0), pct(0.0), "n/a", "n/a", 0, "0%"]]
    holds = {}
    for name, tg in targets.items():
        h = hold_strategy(feat, tg, start25, fee, slip)
        holds[name] = h
        b = base_stats(h.equity)
        rows.append([name, pct(b["total"]), pct(b["cagr"]), pct(b["dd"]), f"{b['calmar']:.2f}", f"{b['sharpe']:.2f}", h.trades,
                     f"{tg.shift(1).fillna(False).mean():.0%}"])
    b = base_stats(s25.equity)
    rows.append(["**Current strategy ($25, risk schedule)**", pct(b["total"]), pct(b["cagr"]), pct(b["dd"]), f"{b['calmar']:.2f}",
                 f"{b['sharpe']:.2f}", e25["trades"], f"{e25['time_in_mkt']:.0%}"])
    be = base_stats(base_res_edge.equity)
    rows.append(["Current strategy (edge test, 100k at 2%)", pct(be["total"]), pct(be["cagr"]), pct(be["dd"]), f"{be['calmar']:.2f}",
                 f"{be['sharpe']:.2f}", full_edge["trades"], f"{full_edge['time_in_mkt']:.0%}"])
    L += table(["Approach", "Total return", "CAGR", "Max DD", "Calmar", "Sharpe", "Trades", "Time invested"], rows)
    L += [f"Starting from $25, buy & hold ends at ${holds['BTC buy & hold'].equity.iloc[-1]:,.2f}; the strategy ends at "
          f"${s25.equity.iloc[-1]:,.2f}.", ""]
    L += ["**Risk-matched comparison.** Buy & hold wins on raw return only by carrying a much larger drawdown. Holding just "
          "enough BTC (the rest in USDT, no leverage) so each baseline's max drawdown equals the strategy's:", ""]
    mrows = []
    for label, strat_eq in (("$25 account", s25.equity), ("Edge test", base_res_edge.equity)):
        tdd = max_drawdown(strat_eq)
        sb = base_stats(strat_eq)
        mrows.append([label, "Current strategy", "100%", pct(sb["total"]), pct(sb["dd"])])
        for name, h in holds.items():
            sc, w = scale_to_drawdown(h.equity, tdd)
            sbs = base_stats(sc)
            mrows.append([label, name, f"{w:.0%} in BTC", pct(sbs["total"]), pct(sbs["dd"])])
    L += table(["Compared at", "Approach", "Exposure used", "Total return", "Max DD"], mrows)
    L += ["(Scaling is an approximation: daily-rebalanced fraction, trading costs not re-scaled.)", ""]

    L += ["**Ablation: which rule components carry the result?** Edge test, base fills.", ""]
    abl_rows = []
    for m in (True, False):
        for d in (True, False):
            for mac in (True, False):
                for pb in (True, False):
                    f = ablation(feat, m, d, mac, pb)
                    res = run_backtest(f, base, universe, EDGE_CAPITAL, EDGE_RISK)
                    e = economics(res)
                    abl_rows.append([("1M " if m else "") + ("1D " if d else "") + ("macro " if mac else "") + ("pullback" if pb else "(no pullback timing)"),
                                     e["trades"], pct(e["total_return"]), pct(e["max_dd"]), f"{e['avg_R']:+.2f}",
                                     f"{e['total_return'] / max(abs(e['max_dd']), 0.01):.1f}"])
    L += table(["Components ON", "Trades", "Return", "Max DD", "Avg R", "Return / DD"], abl_rows)
    L += ["Reading this table: component choices change return by large amounts in both directions (for example the 1M-only "
          "rows earn more than the full rule set, with similar drawdown). That is a statement about how noisy ~50-140 "
          "trades are, not a reason to switch to the best row: choosing it now would be exactly the in-sample selection "
          "this audit is meant to avoid.", ""]

    L += ["**Circuit breakers on vs off** (3 losses -> 7-day pause; 5% below peak -> 30-day pause):", ""]
    nb_rules = copy.deepcopy(base)
    nb_rules["risk"].update(max_consecutive_losses=10_000, floor_pct=1.0)
    rows = []
    for label, rr in (("breakers on (current)", base), ("breakers off", nb_rules)):
        e = economics(run_backtest(feat, rr, universe, EDGE_CAPITAL, EDGE_RISK))
        s = economics(run_backtest(feat, rr, universe, 25.0))
        rows.append([label, e["trades"], pct(e["total_return"]), pct(e["max_dd"]), f"{e['avg_R']:+.2f}",
                     f"{s['final']:.2f}", pct(s["max_dd"])])
    L += table(["Setting", "Edge trades", "Edge return", "Edge max DD", "Edge avg R", "$25 final", "$25 max DD"], rows)

    # frontier
    L += ["**Risk appetite frontier for the simple trend baseline** (hold BTC while above its 200-day SMA, else USDT; only a "
          "fraction of the account is ever in BTC, the rest stays USDT; no leverage). This shows what $25 and $300 would "
          "have done at different risk levels, so the trade-off is explicit:", ""]
    sb = holds["Simple trend: BTC above its 200-day SMA, else USDT"].equity
    bb = holds["BTC buy & hold"].equity
    rows = []
    for w in (0.10, 0.25, 0.50, 1.00):
        for label, h in (("200-day trend", sb), ("buy & hold", bb)):
            ret = h.pct_change().fillna(0.0)
            eqw = (1 + w * ret).cumprod()
            b = base_stats(eqw)
            rows.append([f"{w:.0%} of account in BTC", label, pct(b["total"]), pct(b["cagr"]), pct(b["dd"]),
                         f"${25 * eqw.iloc[-1]:,.0f}", f"${300 * eqw.iloc[-1]:,.0f}"])
    L += table(["Exposure", "Approach", "Total return", "CAGR", "Max DD", "$25 becomes", "$300 becomes"], rows)
    L += ["These are 2018-2026 BTC results, a period in which BTC rose ~7x; they are not a forecast and the deep drawdowns "
          "are the price of the returns.", ""]

    # placebo
    pl = placebo(feat, base, universe, placebo_runs)
    real_rd = full_edge["total_return"] / max(abs(full_edge["max_dd"]), 0.01)
    L += [f"**Placebo test ({placebo_runs} runs).** Same gate, exits and sizing; entry days chosen at random "
          f"(probability {pl['p']:.0%} per eligible day, matching the real signal frequency). Real strategy: return "
          f"{pct(full_edge['total_return'])}, return/DD {real_rd:.1f}, avg R {full_edge['avg_R']:+.2f}.", "",
          f"- Random entries: median return {pct(np.median(pl['ret']))} (5th-95th pct {pct(np.percentile(pl['ret'], 5))} to "
          f"{pct(np.percentile(pl['ret'], 95))}); median return/DD {np.median(pl['ret_dd']):.1f}; median avg R "
          f"{np.median(pl['avg_r']):+.2f}.",
          f"- The real pullback signal beats {np.mean(pl['ret'] < full_edge['total_return']):.0%} of random-entry runs on "
          f"return, {np.mean(pl['ret_dd'] < real_rd):.0%} on return/DD, {np.mean(pl['avg_r'] < full_edge['avg_R']):.0%} on avg R.", ""]

    # 5. per-capital economics ----------------------------------------------------------------------------------
    L += ["## 5. Economics by starting capital", "",
          "Current risk schedule (2% of equity below 50 USDT, 1% above), Binance minimum order 5 USDT x 1.1, qty step "
          "0.00001 BTC. Dollar = USDT.", ""]
    harsh_rules = ladder(base)[4][1]
    per_cap_base, per_cap_harsh = {}, {}
    for cap in CAPITALS:
        per_cap_base[f"${cap:,.0f}"] = (run_backtest(feat, base, universe, cap))
        per_cap_harsh[f"${cap:,.0f}"] = (run_backtest(feat, harsh_rules, universe, cap))
    L += ["### Base fill model, full period (" + f"{feat.index[0].date()} to {feat.index[-1].date()})", ""]
    L += econ_table({k: economics(v) for k, v in per_cap_base.items()})
    for cap in CAPITALS:
        L.append("    " + summary_block(cap, economics(per_cap_base[f"${cap:,.0f}"])))
    L += ["", "### Out-of-sample only (2023-01 onward), base fills", ""]
    L += econ_table({k: economics(v, SPLIT) for k, v in per_cap_base.items()})
    L += ["### Harsh fill model, full period", ""]
    L += econ_table({k: economics(v) for k, v in per_cap_harsh.items()})
    skipped = {k: sum(v.skipped.values()) for k, v in per_cap_base.items()}
    L += ["Signals skipped because the position would fall below Binance's minimum order (base fills): "
          + ", ".join(f"{k}: {n} of {v.plans + sum(v.skipped.values())}" for (k, n), v in zip(skipped.items(), per_cap_base.values())),
          ""]
    L += ["Same capitals at a flat 2% risk (to show how much of the dollar result is just the risk budget):", ""]
    L += econ_table({f"${c:,.0f}": economics(run_backtest(feat, base, universe, c, 0.02)) for c in CAPITALS})

    # profit concentration
    r = full_edge["R"]
    order = np.sort(r)[::-1]
    L += ["### Where the profit comes from (edge test)", "",
          f"- {len(r)} trades, sum of R = {r.sum():+.1f}. Best single trade {order[0]:+.1f}R; top 3 trades {order[:3].sum():+.1f}R "
          f"({order[:3].sum() / r.sum():.0%} of the total); without the top 3, the remaining {len(r) - 3} trades sum to "
          f"{order[3:].sum():+.1f}R (avg {order[3:].mean():+.2f}R).",
          f"- Win rate {full_edge['win_rate']:.0%}; median R {np.median(r):+.2f}; trades above +2R: {int((r > 2).sum())}.", ""]

    # required capital
    ann = {k: economics(v)["cagr"] for k, v in per_cap_base.items()}
    a300, a_oos = ann["$300"], economics(per_cap_base["$300"], SPLIT)["cagr"]
    L += ["### What capital would $1/day need?", ""]
    rows = []
    for label, a in (("full period CAGR at $300", a300), ("out-of-sample CAGR at $300", a_oos),
                     ("halved (shrinkage for overfitting)", a300 / 2)):
        rows.append([label, pct(a), "never" if not a > 0 else f"${365 / a:,.0f}", "never" if not a > 0 else f"${36.5 / a:,.0f}"])
    L += table(["Return assumption", "Annual return", "Capital for $1/day ($365/yr)", "Capital for $0.10/day"], rows)
    L += ["(Linear scaling of the 1%-risk results; assumes the same trade quality at larger size, which holds for BTC at "
          "these amounts.)", ""]

    # 6. Monte Carlo --------------------------------------------------------------------------------------------
    L += ["## 6. Monte Carlo", "",
          f"Resampling the observed per-trade returns (fraction of equity at entry) with a Poisson number of trades "
          f"per year. {len(economics(per_cap_base['$25'])['pnl'])} trades is a small sample: these ranges describe the "
          "shape of the risk, not a forecast. Drawdowns are trade-to-trade (intra-trade dips are ignored, "
          "so real drawdowns run somewhat deeper).", ""]
    for cap in (25.0, 300.0):
        res = per_cap_base[f"${cap:,.0f}"]
        e = economics(res)
        fr = np.array([t.pnl / (t.equity_after - t.pnl) for t in res.trades])
        per_year = e["trades"] / e["years"]
        L += [f"### ${cap:,.0f} account ({e['trades']} observed trades, {per_year:.1f}/year, mean {fr.mean():+.2%} of equity per trade)", ""]
        rows = []
        for label, kw in (("as observed", {}), ("clustered streaks (blocks of 3)", {"block": 3}),
                          ("edge halved", {"shift": 0.5}), ("no edge (mean = 0)", {"shift": 1.0})):
            for yrs in (1, 3):
                m = monte_carlo(fr, per_year, yrs, cap, **kw)
                rows.append([label, f"{yrs}y", f"${m['p5']:.2f} / ${m['p50']:.2f} / ${m['p95']:.2f}", f"{m['p_loss']:.0%}",
                             f"{m['p_lose10']:.0%}", f"{m['dd_median']:.1%} / {m['dd_p95']:.1%}", f"{m['p_dd10']:.0%} / {m['p_dd20']:.0%}",
                             f"{m['streak_median']:.0f} / {m['streak_p95']:.0f}"])
        L += table(["Scenario", "Horizon", "Ending capital 5th / median / 95th", "P(end < start)", "P(end < 90% of start)",
                    "Max DD median / worst-5%", "P(DD>=10%) / P(DD>=20%)", "Losing streak median / worst-5%"], rows)

    # 7. parameter neighbourhood -------------------------------------------------------------------------------
    L += ["## 7. Parameter sensitivity (robustness only, not for selection)", "",
          "One change at a time around v2, edge test, base fills. A genuine edge is a plateau; a knife-edge means the "
          "published numbers were luck of the draw.", ""]
    nb = []

    def add(label, mut):
        r = copy.deepcopy(base)
        mut(r)
        f = build_features(btc, macro, r)
        e = economics(run_backtest(f, r, universe, EDGE_CAPITAL, EDGE_RISK))
        nb.append([label, e["trades"], pct(e["total_return"]), pct(e["max_dd"]), f"{e['avg_R']:+.2f}",
                   f"{e['total_return'] / max(abs(e['max_dd']), 0.01):.1f}", e["total_return"], e["avg_R"]])

    add("**v2 base**", lambda r: None)
    for v in (6, 8, 12):
        add(f"monthly SMA {v}", lambda r, v=v: r["regime"].__setitem__("monthly_sma", v))
    for v in (100, 150, 250):
        add(f"EMA slow {v}", lambda r, v=v: r["regime"].__setitem__("ema_slow", v))
    for v in (30, 100):
        add(f"EMA fast {v}", lambda r, v=v: r["regime"].__setitem__("ema_fast", v))
    for v in (10, 30):
        add(f"pullback EMA {v}", lambda r, v=v: r["setup"].__setitem__("ema_pullback", v))
    for v in (45, 65, 100):
        add(f"RSI max {v}", lambda r, v=v: r["setup"].__setitem__("rsi_max", v))
    for v in (0.005, 0.02, 0.03):
        add(f"pullback tolerance {v:.1%}", lambda r, v=v: r["setup"].__setitem__("pullback_tolerance", v))
    for v in ([0.0, 0.5], [0.5, 1.0], [0.25]):
        add(f"ladder offsets {v}", lambda r, v=v: r["entry"].__setitem__("ladder_atr_offsets", v))
    for v in (1, 3):
        add(f"order valid {v}d", lambda r, v=v: r["entry"].__setitem__("valid_days", v))
    for v in (0.75, 1.5):
        add(f"initial stop {v} ATR", lambda r, v=v: r["exit"].__setitem__("stop_atr_mult", v))
    for v in (1.5, 2.5, 3.0):
        add(f"trail {v} ATR", lambda r, v=v: r["exit"].__setitem__("trail_atr_mult", v))
    add("risk-off thresholds doubled", lambda r: r["regime"]["macro"].update(dxy_surge_pct=0.05, gold_spike_pct=0.12, oil_spike_pct=0.20))
    add("S&P gate on 100-day SMA", lambda r: r["regime"]["macro"].__setitem__("spx_sma", 100))
    L += table(["Variation", "Trades", "Return", "Max DD", "Avg R", "Return / DD"], [row[:6] for row in nb])
    rets = np.array([row[6] for row in nb[1:]])
    avg_rs = np.array([row[7] for row in nb[1:]])
    L += [f"{len(rets)} neighbours: {int((rets > 0).sum())} profitable, {int((avg_rs > 0).sum())} with positive average R; "
          f"median neighbour return {pct(np.median(rets))} vs base {pct(nb[0][6])}; "
          f"base beats {np.mean(rets < nb[0][6]):.0%} of its neighbours.", ""]

    # 8. other assets ---------------------------------------------------------------------------------------------
    L += ["## 8. Other assets", "",
          "Multi-asset results (ETH, SOL, ADA, LTC with shared risk and position caps) are in "
          f"`reports/universe_{date.today()}.md`; the Sharia screening notes are in `RESEARCH.md` Appendix A.", ""]

    return "\n".join(L)


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Profitability audit of the current rules.")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--placebo-runs", type=int, default=300)
    args = ap.parse_args()
    text = build_report(args.refresh, args.placebo_runs)
    REPORTS_DIR.mkdir(exist_ok=True)
    path = REPORTS_DIR / f"audit_{date.today()}.md"
    path.write_text(text, encoding="utf-8")
    print(f"Saved to {path} ({len(text.splitlines())} lines)")


if __name__ == "__main__":
    main()
