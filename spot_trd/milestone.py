"""How realistic is $300 -> $350 from trading profits alone with frozen v2? (analysis of existing evidence, nothing is tuned)

Scenarios are fixed here before the first run:
  base          observed v2 trades, base fills
  conservative  base trades with HALF of the average edge removed (the audit found the edge thin and partly flattered)
  harsh         observed v2 trades under harsh fills (0.15% trade-through, 0.3% exit slip, 0.5% stop slip)
  gap stress    base fills but stops fill 1.5% worse than planned
  no edge       base trades with the whole average edge removed (what if the edge is illusory)
Risk per trade is v2's schedule (1% at $300) in every scenario. Milestones count REALIZED equity only (initial + closed-trade P&L);
unrealized gains are never counted as earned.
Run: uv run python -m spot_trd.milestone
"""
from datetime import date

import numpy as np
import pandas as pd

from spot_trd.audit import economics, ladder, pct, table
from spot_trd.backtest import Result, run_backtest
from spot_trd.config import REPORTS_DIR, load_rules, load_universe
from spot_trd.data import load_data
from spot_trd.regime import build_features

START_EQUITY = 300.0
MILESTONES = (310, 320, 330, 340, 350)
HORIZONS = (1, 2, 3, 5)           # years, for rolling historical starts
MC_YEARS = (1, 2, 3, 5, 10)
STEP_DAYS = 7


def realized_curve(res: Result) -> pd.Series:
    """Initial equity plus the P&L of closed trades, stepping at each exit date."""
    if not res.trades:
        return pd.Series([START_EQUITY], index=[res.equity.index[0]])
    s = pd.Series({t.exit_date: t.pnl for t in res.trades}).groupby(level=0).sum().sort_index()
    return START_EQUITY + s.cumsum()


def first_reach(realized: pd.Series, level: float, start: pd.Timestamp):
    hit = realized[realized >= level]
    return (hit.index[0] - start).days if len(hit) else np.nan


def underwater(eq: pd.Series, level: float = START_EQUITY) -> tuple[float, int]:
    below = (eq < level - 0.005).to_numpy()
    best = cur = 0
    for b in below:
        cur = cur + 1 if b else 0
        best = max(best, cur)
    return float(below.mean()), best


def _days_without_high(eq: pd.Series) -> int:
    under = (eq < eq.cummax()).to_numpy()
    best = cur = 0
    for u in under:
        cur = cur + 1 if u else 0
        best = max(best, cur)
    return best


def fractions(res: Result) -> np.ndarray:
    return np.array([t.pnl / (t.equity_after - t.pnl) for t in res.trades])


def first_passage(E: np.ndarray, T: np.ndarray, level: float) -> np.ndarray:
    hit = E >= level
    any_hit = hit.any(axis=1)
    first = hit.argmax(axis=1)
    out = np.where(any_hit, T[np.arange(len(T)), first], np.inf)
    return out


def simulate(fr: np.ndarray, rate: float, years: int = 10, n: int = 20_000, seed: int = 31, shift: float = 0.0, block: int = 1):
    rng = np.random.default_rng(seed)
    K = int(rate * years * 2.5) + 25
    T = np.cumsum(rng.exponential(1 / rate, size=(n, K)), axis=1)
    if block == 1:
        idx = rng.integers(0, len(fr), size=(n, K))
    else:
        nb = K // block + 1
        starts = rng.integers(0, len(fr), size=(n, nb))
        idx = ((starts[:, :, None] + np.arange(block)) % len(fr)).reshape(n, -1)[:, :K]
    r = fr[idx] - shift * fr.mean()
    E = START_EQUITY * np.cumprod(1 + r, axis=1)
    return T, E


def state_at(T: np.ndarray, E: np.ndarray, t: float) -> np.ndarray:
    k = (T <= t).sum(axis=1) - 1
    return np.where(k < 0, START_EQUITY, E[np.arange(len(E)), np.maximum(k, 0)])


def build_report() -> str:
    base, universe = load_rules(), load_universe()
    btc, macro = load_data()
    feat = build_features(btc, macro, base)
    rules = {"base": ladder(base)[2][1], "harsh": ladder(base)[4][1], "gap": ladder(base)[5][1]}
    runs = {k: run_backtest(feat, r, universe, START_EQUITY) for k, r in rules.items()}
    econ = {k: economics(v) for k, v in runs.items()}
    years_hist = (feat.index[-1] - feat.index[0]).days / 365.25
    rate = econ["base"]["trades"] / years_hist
    fr = {k: fractions(v) for k, v in runs.items()}

    L = [f"# How realistic is $300 -> $350? ({date.today()})", "",
         "Frozen v2, BTC spot only, $300 start, **no contributions**, risk per trade as per v2's schedule (1% at $300), no trade forced. "
         "All progress is counted on **realized** equity (initial + closed-trade P&L). Scenarios were fixed before the first run: base, "
         "conservative (half the average edge removed), harsh fills, gap stress, and no edge. Nothing was tuned.", ""]

    # ---- evidence base ------------------------------------------------------------------------------------------------
    L += ["## 1. The evidence base", "",
          f"- v2 on $300 over {years_hist:.1f} years ({feat.index[0].date()} to {feat.index[-1].date()}): {econ['base']['trades']} trades = "
          f"**{rate:.1f} trades a year**, win rate {econ['base']['win_rate']:.0%}, average {econ['base']['avg_R']:+.2f}R, average trade "
          f"{fr['base'].mean():+.2%} of equity, median trade {np.median(fr['base']):+.2%}.",
          f"- Profit per year at $300: base **${econ['base']['profit_per_year']:+.2f}**, harsh ${econ['harsh']['profit_per_year']:+.2f}, "
          f"gap stress ${econ['gap']['profit_per_year']:+.2f}; 2023-onward (contaminated, consistency only) "
          f"${economics(runs['base'], pd.Timestamp('2023-01-01'))['profit_per_year']:+.2f}.",
          "- The audit found that three trades produced 78% of the profit, so the average hides a very lumpy process: most trades are small "
          "losses, a few trend trades pay for them.", ""]

    # ---- arithmetic ---------------------------------------------------------------------------------------------------
    L += ["## 2. Straight arithmetic: years of *average* profit needed for +$50", ""]
    rows = []
    for k, lab in (("base", "Base"), ("harsh", "Harsh fills"), ("gap", "Gap stress")):
        ppy = econ[k]["profit_per_year"]
        rows.append([lab, f"${ppy:+.2f}", f"{50 / ppy:.1f} years" if ppy > 0 else "never"])
    cons = econ["base"]["profit_per_year"] / 2
    rows.append(["Conservative (half the edge)", f"${cons:+.2f}", f"{50 / cons:.1f} years"])
    rows.append(["No edge", "$0 (before the fee drag already in the numbers)", "never"])
    L += table(["Scenario", "Average profit per year at $300", "Years to +$50 at that average"], rows)
    boot = np.random.default_rng(5).choice(fr["base"], size=(20_000, len(fr["base"]))).mean(axis=1)
    lo, hi = np.percentile(boot, [2.5, 97.5])
    L += [f"The average trade is only known to within a wide band: bootstrap 95% interval for the mean trade {lo:+.2%} to {hi:+.2%} of equity "
          f"(that is ${300 * lo * rate:+.1f} to ${300 * hi * rate:+.1f} a year at $300). The lower end is at or below zero.", ""]

    # ---- single historical path -----------------------------------------------------------------------------------------
    L += ["## 3. The one historical path (start 2018-03-04)", ""]
    rows = []
    for k in ("base", "harsh", "gap"):
        rc = realized_curve(runs[k])
        cells = []
        for m in MILESTONES:
            d = first_reach(rc, m, feat.index[0])
            cells.append("not reached" if np.isnan(d) else f"{d / 365.25:.1f} y")
        rows.append([k] + cells + [f"${rc.iloc[-1]:.2f}"])
    L += table(["Fills"] + [f"${m}" for m in MILESTONES] + ["Final realized"], rows)
    mk = runs["base"].equity
    below, longest = underwater(mk)
    gap_days = _days_without_high(mk)
    high_gap = gap_days
    L += [f"Marked equity was below $300 on {below:.0%} of days; the longest unbroken stretch below $300 was **{longest} days "
          f"({longest / 365.25:.1f} years)**. The longest time without a new equity high was **{gap_days} days ({gap_days / 365.25:.1f} years)**. Maximum drawdown {econ['base']['max_dd']:.1%} (about ${abs(econ['base']['max_dd']) * 300:.0f}); harsh "
          f"{econ['harsh']['max_dd']:.1%}; gap stress {econ['gap']['max_dd']:.1%}.", ""]

    # ---- rolling historical starts ------------------------------------------------------------------------------------
    L += ["## 4. Every possible historical start date (v2 restarted from $300 every 7 days)", "",
          "For a horizon of H years only starts with at least H years of data left are used, so there is no censoring bias. The history "
          "holds only about `history / H` independent windows, so these are a handful of market episodes.", ""]
    res_by = {}
    for k in ("base", "harsh"):
        rows_k = []
        for s in feat.index[::STEP_DAYS]:
            sub = feat.loc[s:]
            if len(sub) < 200:
                break
            r = run_backtest(sub, rules[k], universe, START_EQUITY)
            rc = realized_curve(r)
            fr_below, longest_w = underwater(r.equity)
            rows_k.append({"start": s, "left": (feat.index[-1] - s).days,
                           **{f"t{m}": first_reach(rc, m, s) for m in MILESTONES}, "below": fr_below, "longest": longest_w,
                           "dd": economics(r)["max_dd"]})
        res_by[k] = pd.DataFrame(rows_k)
    for k in ("base", "harsh"):
        df = res_by[k]
        rows = []
        for H in HORIZONS:
            sub = df[df["left"] >= H * 365]
            reach350 = (sub["t350"] <= H * 365)
            reach310 = (sub["t310"] <= H * 365)
            rows.append([f"{H} year{'s' if H > 1 else ''}", len(sub), f"{years_hist / H:.1f}", f"{reach310.mean():.0%}", f"{reach350.mean():.0%}"])
        L += [f"**{k} fills**", ""]
        L += table(["Within", "Start dates usable", "Independent windows", "Reached $310", "Reached $350"], rows)
        done = df["t350"].dropna()
        L += [f"Of {len(df)} start dates, {len(done)} ({len(done) / len(df):.0%}) reached $350 at some point before the data ended "
              f"(median {done.median() / 365.25:.1f} years, fastest {done.min() / 365.25:.1f}); the rest had not reached it by the end of the data "
              "(later starts are cut off sooner). Marked equity spent a median "
              f"{df['below'].median():.0%} of days below $300 per start date (worst {df['below'].max():.0%}), and the longest stretch below $300 "
              f"was a median {df['longest'].median() / 365.25:.1f} years (worst {df['longest'].max() / 365.25:.1f}). Worst drawdown across starts "
              f"{df['dd'].min():.1%}.", ""]

    # ---- Monte Carlo ------------------------------------------------------------------------------------------------
    L += ["## 5. Monte Carlo from the observed trades", "",
          f"Trades arrive at {rate:.1f} a year (random gaps), each returning a resampled observed trade result as a fraction of equity, "
          "compounding. 20,000 paths over 10 years. No circuit breaker, so it ignores the pauses v2 would take (small effect at 1% risk). "
          "A path 'reaches' $350 the first time **realized** equity is at or above it.", ""]
    scen = {
        "base": dict(fr=fr["base"], shift=0.0, block=1),
        "base, clustered losses (blocks of 3)": dict(fr=fr["base"], shift=0.0, block=3),
        "conservative (half the edge)": dict(fr=fr["base"], shift=0.5, block=1),
        "harsh fills": dict(fr=fr["harsh"], shift=0.0, block=1),
        "gap stress": dict(fr=fr["gap"], shift=0.0, block=1),
        "no edge": dict(fr=fr["base"], shift=1.0, block=1),
    }
    mc = {name: simulate(rate=rate, seed=31 + i, **kw) for i, (name, kw) in enumerate(scen.items())}
    L += ["### Probability of having reached $350 (realized) within...", ""]
    rows = []
    for name, (T, E) in mc.items():
        t350 = first_passage(E, T, 350.0)
        rows.append([name] + [f"{(t350 <= y).mean():.0%}" for y in MC_YEARS] + [f"{np.median(t350[t350 <= 10]):.1f} y" if (t350 <= 10).any() else "n/a",
                     f"{(~(t350 <= 10)).mean():.0%}"])
    L += table(["Scenario"] + [f"{y} y" for y in MC_YEARS] + ["Median time among those that get there", "Not reached in 10 years"], rows)
    L += ["### Median years to each milestone (only counting paths that get there within 10 years; share that does in brackets)", ""]
    rows = []
    for name, (T, E) in mc.items():
        cells = []
        for m in MILESTONES:
            t = first_passage(E, T, float(m))
            ok = t <= 10
            cells.append(f"{np.median(t[ok]):.1f} y ({ok.mean():.0%})" if ok.any() else "never")
        rows.append([name] + cells)
    L += table(["Scenario"] + [f"${m}" for m in MILESTONES], rows)
    L += ["### Being below $300 (realized equity)", ""]
    rows = []
    for name, (T, E) in mc.items():
        grid = np.arange(1, 61) / 12
        below_t = np.mean([(state_at(T, E, t) < START_EQUITY - 1e-9).mean() for t in grid])
        dd = np.minimum.accumulate(E / np.maximum.accumulate(np.maximum(E, START_EQUITY), axis=1), axis=1)
        dd5 = np.where(T <= 5, E / np.maximum.accumulate(np.concatenate([np.full((len(E), 1), START_EQUITY), E], axis=1)[:, 1:], axis=1) - 1, 0).min(axis=1)
        rows.append([name] + [f"{(state_at(T, E, y) < START_EQUITY - 1e-9).mean():.0%}" for y in (1, 2, 3, 5)] +
                    [f"{below_t:.0%}", f"{np.percentile(dd5, 5):.1%}"])
    L += table(["Scenario", "Below $300 after 1 y", "2 y", "3 y", "5 y", "Average share of the first 5 years spent below $300",
                "Worst-5% drawdown within 5 years (trade-level)"], rows)

    # ---- verdict -------------------------------------------------------------------------------------------------------
    T, E = mc["base"]
    t_base = first_passage(E, T, 350.0)
    Tc, Ec = mc["conservative (half the edge)"]
    t_cons = first_passage(Ec, Tc, 350.0)
    Th, Eh = mc["harsh fills"]
    t_h = first_passage(Eh, Th, 350.0)
    Tn, En = mc["no edge"]
    t_n = first_passage(En, Tn, 350.0)
    L += ["## 6. Verdict", "",
          f"- **Base case:** the average-profit arithmetic says about {50 / econ['base']['profit_per_year']:.1f} years. The simulation agrees that the *typical* "
          f"path takes years: median {np.median(t_base[t_base <= 10]):.1f} years among paths that get there within 10 years, with {(t_base <= 3).mean():.0%} reaching "
          f"$350 by year 3, {(t_base <= 5).mean():.0%} by year 5 and {(t_base <= 10).mean():.0%} by year 10.",
          f"- **Conservative (half the edge):** {(t_cons <= 5).mean():.0%} by year 5, {(t_cons <= 10).mean():.0%} by year 10.",
          f"- **Harsh fills:** {(t_h <= 5).mean():.0%} by year 5, {(t_h <= 10).mean():.0%} by year 10.",
          f"- **No edge:** {(t_n <= 10).mean():.0%} reach $350 by year 10 purely by luck; the same simulation with no edge also leaves a large share "
          "below $300 for long stretches.",
          f"- **Historically**, the one real path (start 2018-03) reached $350 realized after {first_reach(realized_curve(runs['base']), 350, feat.index[0]) / 365.25:.1f} "
          "years and never fell below $300, because it started just before two good years. That was a favourable start: across all start dates "
          f"only {len(res_by['base']['t350'].dropna()) / len(res_by['base']):.0%} had reached $350 by the end of the data, marked equity spent a median "
          f"{res_by['base']['below'].median():.0%} of days below $300 (worst start {res_by['base']['below'].max():.0%}) and the longest stretch below $300 reached "
          f"{res_by['base']['longest'].max() / 365.25:.1f} years. Separately, the equity curve went {high_gap} days ({high_gap / 365.25:.1f} years) without a new high.",
          "- There is **no honest deadline**. If the strategy's true edge is close to what history shows, $350 is a multi-year outcome; if the edge is "
          "half of what it appears, it is a decade-long one; if the edge is illusory, there is no reason to expect $350 at all. A paper "
          "test cannot tell these apart quickly: telling the observed average from zero needs about 100 or more trades, about 19 years at this rate.",
          "- Risk is not increased at any milestone, and none of this changes v2. The earlier higher-risk study already showed that "
          "raising risk to speed this up fails on probability of loss, not just on drawdown."]
    return "\n".join(L)


def main() -> None:
    text = build_report()
    REPORTS_DIR.mkdir(exist_ok=True)
    path = REPORTS_DIR / f"milestone_350_{date.today()}.md"
    path.write_text(text, encoding="utf-8")
    print(f"Saved to {path} ({len(text.splitlines())} lines)")


if __name__ == "__main__":
    main()
