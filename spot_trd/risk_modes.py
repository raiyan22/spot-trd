"""Can v2 with higher per-trade risk plausibly reach +16.7% ($300 -> $350) in 3-6 months? (pre-registered, research only)

Criteria: reports/risk_modes_preregistration_2026-10-02.md, written before any result existed. The multiples are fixed there;
nothing is tuned to hit the target. v2 itself is untouched: only the risk percentage is overridden from outside.
Run: uv run python -m spot_trd.risk_modes
"""
import json
from datetime import date

import numpy as np
import pandas as pd

from spot_trd.audit import economics, ladder, pct, table
from spot_trd.backtest import run_backtest
from spot_trd.config import REPORTS_DIR, ROOT, load_rules, load_universe
from spot_trd.data import load_data
from spot_trd.regime import build_features

# ---- pre-registered constants ------------------------------------------------------------------------------------------
CAPITAL, TARGET_CAPITAL = 300.0, 350.0
TARGET = TARGET_CAPITAL / CAPITAL - 1          # +16.67%
BASE_RISK = 0.01
MULTIPLES = (1, 2, 3, 5)
GATED = {"3 months": 91, "6 months": 182}
INFO = {"12 months": 365, "24 months": 730}
STEP_DAYS = 7
MAX_BOUNDED_RISK = 0.03
R1_REACH, R2_LOSS, R3_DD_PROB, R3_DD, R4_P5, R4_WORST = 0.50, 0.20, 0.10, 0.20, -0.15, -0.25


def run_windows(feat: pd.DataFrame, rules: dict, universe: dict, risk: float, days: int) -> pd.DataFrame:
    rows, idx = [], feat.index
    for k in range(0, len(idx), STEP_DAYS):
        start, end = idx[k], idx[k] + pd.Timedelta(days=days)
        if end > idx[-1]:
            break
        res = run_backtest(feat.loc[start:end], rules, universe, CAPITAL, risk)
        eq = res.equity
        rows.append({"start": start, "end_ret": eq.iloc[-1] / CAPITAL - 1, "touched": eq.max() >= TARGET_CAPITAL,
                     "maxdd": float((eq / np.maximum.accumulate(eq) - 1).min()), "trades": len(res.trades),
                     "halts": len(res.halts)})
    return pd.DataFrame(rows)


def summarize_windows(w: pd.DataFrame) -> dict:
    return {
        "n": len(w), "p_reach": float((w.end_ret >= TARGET - 1e-12).mean()), "p_touch": float(w.touched.mean()),
        "p_loss": float((w.end_ret < -1e-9).mean()), "p_lose10": float((w.end_ret <= -0.10).mean()),
        "p_lose20": float((w.end_ret <= -0.20).mean()), "median": float(w.end_ret.median()),
        "p5": float(w.end_ret.quantile(0.05)), "p95": float(w.end_ret.quantile(0.95)), "worst": float(w.end_ret.min()),
        "dd_median": float(w.maxdd.median()), "dd_p95": float(w.maxdd.quantile(0.05)),
        "p_dd20": float((w.maxdd <= -R3_DD).mean()), "p_idle": float((w.trades == 0).mean()),
    }


def monte_carlo(R: np.ndarray, per_year: float, days: int, risk: float, n: int = 40_000, seed: int = 21) -> dict:
    rng = np.random.default_rng(seed)
    counts = rng.poisson(per_year * days / 365, size=n)
    ends, dds = np.empty(n), np.empty(n)
    for s in range(n):
        path = np.concatenate([[1.0], np.cumprod(1 + rng.choice(R, size=counts[s]) * risk)]) if counts[s] else np.array([1.0])
        ends[s] = path[-1] - 1
        dds[s] = (path / np.maximum.accumulate(path) - 1).min()
    return {"p_reach": float((ends >= TARGET).mean()), "p_loss": float((ends < -1e-9).mean()), "p_lose10": float((ends <= -0.10).mean()),
            "p5": float(np.percentile(ends, 5)), "worst": float(np.percentile(ends, 0.5)), "median": float(np.median(ends)),
            "p_dd20": float((dds <= -R3_DD).mean()), "dd_p95": float(np.percentile(dds, 5)), "p_idle": float((counts == 0).mean())}


def criteria(h: dict, mc: dict, risk: float, harsh: dict | None) -> dict:
    def r1234(x, worst_key="worst"):
        return {"R1": x["p_reach"] >= R1_REACH, "R2": x["p_loss"] <= R2_LOSS, "R3": x["p_dd20"] <= R3_DD_PROB,
                "R4": x["p5"] >= R4_P5 and x[worst_key] >= R4_WORST}
    hist, sim = r1234(h), r1234(mc)
    out = dict(hist)
    out["R2h"], out["R3h"], out["R4h"] = (False, False, False) if harsh is None else tuple(
        r1234(harsh)[k] for k in ("R2", "R3", "R4"))
    out["R5"] = all(hist[k] == sim[k] for k in ("R1", "R2", "R3", "R4"))
    out["R6"] = risk <= MAX_BOUNDED_RISK + 1e-12
    return out


def build_report() -> str:
    base, universe = load_rules(), load_universe()
    btc, macro = load_data()
    feat = build_features(btc, macro, base)
    rb, rh = ladder(base)[2][1], ladder(base)[4][1]

    edge = run_backtest(feat, rb, universe, 100_000.0, 0.02)
    e = economics(edge)
    R, per_year = e["R"], e["trades"] / e["years"]
    eh = economics(run_backtest(feat, rh, universe, 100_000.0, 0.02))

    freeze = json.loads((ROOT / "reports" / "risk_modes_freeze_2026-10-02.json").read_text(encoding="utf-8"))
    import hashlib
    changed = [f for f, d in freeze["sha256"].items() if hashlib.sha256((ROOT / f).read_bytes()).hexdigest() != d]
    L = [f"# Higher-risk v2: can it reach +{TARGET:.1%} in 3-6 months? ({date.today()})", "",
         f"Pre-registration: `risk_modes_preregistration_2026-10-02.md` (frozen {freeze['frozen_at_utc']}); frozen files unchanged: "
         f"**{'YES' if not changed else 'NO ' + str(changed)}**. $300 start, target $350, v2 rules untouched, circuit breakers on. "
         f"History {feat.index[0].date()} to {feat.index[-1].date()}.", ""]

    # ---- arithmetic ---------------------------------------------------------------------------------------------------
    sig = feat[feat["signal"]]
    dist = 1.25 * sig["atr"] / (sig["close"] - 0.5 * sig["atr"])      # (avg entry - stop) / avg entry for the standard ladder
    L += ["## 1. Arithmetic first", "",
          f"- v2's observed trade rate is {per_year:.1f} per year, so about {per_year * 91 / 365:.1f} trades in 3 months and "
          f"{per_year * 182 / 365:.1f} in 6 months. It is also idle: in the 6-month windows below, the share with **zero trades** is "
          "reported per multiple.",
          f"- Average result per trade: {e['avg_R']:+.2f}R (base), {eh['avg_R']:+.2f}R (harsh); median trade {np.median(R):+.2f}R; "
          f"win rate {e['win_rate']:.0%}; spread of trade results (SD) {R.std(ddof=1):.2f}R."]
    for lab, days in (("3 months", 91), ("6 months", 182)):
        er = e["avg_R"] * per_year * days / 365
        L.append(f"- **{lab}:** expected total about {er:+.2f}R. For the *expected* return to equal +{TARGET:.1%}, risk per trade "
                 f"would have to be about **{TARGET / er:.0%} of capital** (harsh fills: {TARGET / (eh['avg_R'] * per_year * days / 365):.0%}). "
                 "That is the average case; the typical case is worse because the median trade loses.")
    L += [f"- **Spot-only ceiling.** With no leverage, a fully invested position can lose at most its stop distance. On v2's "
          f"{len(sig)} historical signal days the standard ladder's stop distance is a median {dist.median():.1%} "
          f"(10th-90th percentile {dist.quantile(.1):.1%} to {dist.quantile(.9):.1%}), so risk per trade can never exceed roughly that, "
          "even going all-in on every trade.",
          f"- Required annualised pace: +{TARGET:.1%} in 6 months is about {(1 + TARGET) ** 2 - 1:.0%} a year; in 3 months about "
          f"{(1 + TARGET) ** 4 - 1:.0%} a year. v2's historical rate at 2% risk is {e['cagr']:.1%} a year (edge test).", ""]
    needed = TARGET / (e["avg_R"] * per_year * 182 / 365)
    ceiling = float(dist.quantile(0.1))
    arithmetic_reject = needed > ceiling

    # ---- rolling windows ---------------------------------------------------------------------------------------------
    H, HH, INFOR = {}, {}, {}
    for m in MULTIPLES:
        for lab, days in GATED.items():
            H[(m, lab)] = summarize_windows(run_windows(feat, rb, universe, m * BASE_RISK, days))
            HH[(m, lab)] = summarize_windows(run_windows(feat, rh, universe, m * BASE_RISK, days))
        for lab, days in INFO.items():
            INFOR[(m, lab)] = summarize_windows(run_windows(feat, rb, universe, m * BASE_RISK, days))
    total_days = (feat.index[-1] - feat.index[0]).days
    L += ["## 2. Rolling historical windows", "",
          f"v2 restarted from $300 every {STEP_DAYS} days. Windows overlap heavily: the history holds only about "
          f"{total_days // 182} independent 6-month windows and {total_days // 91} independent 3-month windows, so read these as "
          "a handful of market episodes, not hundreds of observations.", ""]
    for lab in GATED:
        L += [f"### {lab} (base fills; harsh fills in the last column)", ""]
        rows = []
        for m in MULTIPLES:
            h, hh = H[(m, lab)], HH[(m, lab)]
            rows.append([f"{m}x ({m * BASE_RISK:.0%})", h["n"], f"{h['p_reach']:.0%}", f"{h['p_touch']:.0%}", f"{h['p_loss']:.0%}",
                         f"{h['p_lose10']:.0%} / {h['p_lose20']:.0%}", f"{pct(h['median'])}", f"{pct(h['p5'])} / {pct(h['worst'])}",
                         f"{h['dd_median']:.1%} / {h['dd_p95']:.1%}", f"{h['p_dd20']:.0%}", f"{h['p_idle']:.0%}",
                         f"{hh['p_reach']:.0%} / {hh['p_loss']:.0%}"])
        L += table(["Risk per trade", "Windows", "P(end >= +16.7%)", "P(touches $350)", "P(end < start)", "P(<= -10% / -20%)",
                    "Median end", "5th pct / worst", "Max DD median / worst-5%", "P(DD >= 20%)", "No trades", "Harsh: reach / loss"], rows)

    # ---- Monte Carlo -------------------------------------------------------------------------------------------------
    L += ["## 3. Monte Carlo from observed trade results", "",
          f"Resampling the {e['trades']} observed R multiples (edge test, base fills) at {per_year:.1f} trades a year. No circuit breaker and "
          "no cash cap, so it slightly overstates both gains and losses at high multiples. MC 'worst' is the 0.5th percentile.", ""]
    MC = {}
    rows = []
    for lab, days in GATED.items():
        for m in MULTIPLES:
            mc = monte_carlo(R, per_year, days, m * BASE_RISK)
            MC[(m, lab)] = mc
            rows.append([lab, f"{m}x ({m * BASE_RISK:.0%})", f"{mc['p_reach']:.0%}", f"{mc['p_loss']:.0%}", f"{mc['p_lose10']:.0%}",
                         f"{pct(mc['median'])}", f"{pct(mc['p5'])} / {pct(mc['worst'])}", f"{mc['dd_p95']:.1%}", f"{mc['p_dd20']:.0%}",
                         f"{mc['p_idle']:.0%}"])
    L += table(["Horizon", "Risk per trade", "P(end >= +16.7%)", "P(end < start)", "P(<= -10%)", "Median end", "5th pct / worst",
                "Max DD worst-5%", "P(DD >= 20%)", "No trades"], rows)

    # ---- criteria ---------------------------------------------------------------------------------------------------
    L += ["## 4. Pre-registered criteria (6-month horizon)", "",
          "R1 reach >= 50%; R2 loss <= 20% (also harsh); R3 P(DD >= 20%) <= 10% (also harsh); R4 5th percentile >= -15% and worst >= -25% "
          "(also harsh); R5 history and Monte Carlo agree on R1-R4; R6 risk per trade <= 3%.", ""]
    rows, accepted = [], []
    for m in MULTIPLES:
        c = criteria(H[(m, "6 months")], MC[(m, "6 months")], m * BASE_RISK, HH[(m, "6 months")])
        ok = all(c.values())
        if ok:
            accepted.append(m)
        mark = lambda b: "PASS" if b else "**FAIL**"
        rows.append([f"{m}x ({m * BASE_RISK:.0%})", mark(c["R1"]), mark(c["R2"] and c["R2h"]), mark(c["R3"] and c["R3h"]),
                     mark(c["R4"] and c["R4h"]), mark(c["R5"]), mark(c["R6"]), "**ACCEPTABLE**" if ok else "**REJECTED**"])
    L += table(["Risk per trade", "R1 reach", "R2 loss", "R3 drawdown", "R4 tail", "R5 history = MC", "R6 bounded", "Result"], rows)

    # ---- informational longer horizons ------------------------------------------------------------------------------
    L += ["## 5. How long would +16.7% plausibly take? (descriptive only; not used to pick a multiple)", ""]
    rows = []
    for m in MULTIPLES:
        cells = []
        for lab in ("6 months", "12 months", "24 months"):
            s = H[(m, lab)] if lab in GATED else INFOR[(m, lab)]
            cells.append(f"{s['p_reach']:.0%} reach, {s['p_loss']:.0%} loss, median {pct(s['median'])}")
        rows.append([f"{m}x ({m * BASE_RISK:.0%})"] + cells)
    L += table(["Risk per trade", "6 months", "12 months", "24 months"], rows)

    # ---- forward evidence --------------------------------------------------------------------------------------------
    mean, sd = R.mean(), R.std(ddof=1)
    n_need = ((1.96 + 0.84) * sd / mean) ** 2
    L += ["## 6. Could a paper test validate a higher-risk mode?", "",
          f"To tell an average of {mean:+.2f}R per trade (SD {sd:.2f}R) from zero with 80% power you need about **{n_need:.0f} trades**. "
          f"At {per_year:.1f} trades a year that is about **{n_need / per_year:.0f} years** of forward paper trading. A year of paper results "
          f"(about {per_year:.0f} trades) cannot confirm expectancy; it can only reveal gross breakage. Raising risk does not change this: "
          "expectancy in R is the same at every multiple, while the dollar swings grow.", ""]

    # ---- verdict ---------------------------------------------------------------------------------------------------
    L += ["## 7. Verdict", ""]
    if arithmetic_reject:
        L.append(f"- **Arithmetic rejects the target.** Making the expected 6-month return equal +{TARGET:.1%} needs about {needed:.0%} risk per trade. "
                 f"A spot position can lose at most its stop distance: a median {dist.median():.1%} of the position, {ceiling:.1%} at the 10th percentile. "
                 "Even investing everything in every trade could not reach the required risk.")
    if accepted:
        L.append(f"- Multiples meeting every criterion: {', '.join(f'{m}x' for m in accepted)}. (Not a recommendation: see section 6.)")
    else:
        L.append("- **No predetermined multiple meets R1-R6. The +16.7% in 3-6 months target is rejected for v2.**")
    h5, h2 = H[(5, "6 months")], H[(2, "6 months")]
    L.append(f"- For scale: at 5x the chance of ending 6 months at or above target was {h5['p_reach']:.0%} while the chance of ending below "
             f"the start was {h5['p_loss']:.0%}; at 2x the figures were {h2['p_reach']:.0%} and {h2['p_loss']:.0%}.")
    best_reach = max(H[(m, "6 months")]["p_reach"] for m in MULTIPLES)
    L += ["", "## 8. Reading notes", "",
          f"- **R1 alone rejects every multiple** (best case {best_reach:.0%} reach against the 50% bar). R2 as written (any loss at all in at "
          "most 20% of windows) is strict: v2 ends a 6-month window slightly below its start in about 40% of windows even at 1x, because it "
          "takes small losses between rare winners. How big the losses are matters more: see the 'P(<= -10% / -20%)' and 5th-percentile "
          "columns, where 1x to 3x stay small and 5x reaches about -11% at the 5th percentile and -15% at the worst window.",
          "- The 12 and 24 month rows are not monotonic in risk (for example 3x reaches the target less often than 2x at 24 months). Two "
          "reasons: v2's circuit breaker (5% below peak pauses new entries for 30 days) fires far more often as risk rises, and there are "
          "only about four independent 24-month windows in the history. Treat those rows as episodes, not statistics.",
          "- Reaching $350 at some point inside a window (the 'touches' column) is not the same as ending there: v2 has no profit target, "
          "so gains are given back if the trade is not closed at the right moment."]
    return "\n".join(L)


def main() -> None:
    text = build_report()
    REPORTS_DIR.mkdir(exist_ok=True)
    path = REPORTS_DIR / f"risk_modes_{date.today()}.md"
    path.write_text(text, encoding="utf-8")
    print(f"Saved to {path} ({len(text.splitlines())} lines)")


if __name__ == "__main__":
    main()
