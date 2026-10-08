"""Is frozen v2 economically worth continuing at the capital you actually have, and would more capital change that?

Analysis of existing evidence (nothing is tuned, v2 is untouched). Risk per trade follows v2's own schedule at every capital
(2% below 50 USDT, 1% above), exactly as in the live card. No trade is forced and risk is never raised.
Reference income levels below are only yardsticks: $10, $50 and $100 a month. You decide what is meaningful.
Run: uv run spot capital        (re-run any time; it rebuilds from the current data)
"""
from datetime import date

import numpy as np
import pandas as pd

from spot_trd.audit import economics, ladder, pct, table
from spot_trd.backtest import run_backtest
from spot_trd.config import REPORTS_DIR, load_rules, load_universe
from spot_trd.data import load_data
from spot_trd.milestone import fractions
from spot_trd.regime import build_features

CAPS = (25, 50, 75, 100, 125, 150, 200, 300, 325, 350, 400, 500)
START_CAPS = (25, 100, 300)
ADDITIONS = (0, 25, 50, 100)                 # per year; the user's ceiling is 100 in any single year
HORIZONS = {"end of 2029": 3.25, "end of 2030": 4.25}      # years from 2026-10-02
REFERENCE = {"$10 a month": 120.0, "$50 a month": 600.0, "$100 a month": 1200.0}
BINS = (25, 50, 300)                          # equity < 50 uses the $25 run, 50 to 100 the $50 run, 100+ the $300 run


def static_row(feat, rules, universe, cap):
    res = run_backtest(feat, rules, universe, float(cap))
    e = economics(res)
    fr = fractions(res)
    skipped = sum(v for k, v in res.skipped.items() if "minimum" in k)
    rate = e["trades"] / e["years"]
    boot = np.random.default_rng(3).choice(fr, size=(10_000, len(fr))).mean(axis=1)
    lo, hi = np.percentile(boot, [2.5, 97.5])
    avg_pos = np.mean([t.cost for t in res.trades]) if res.trades else 0.0
    return {"cap": cap, "e": e, "rate": rate, "skip": skipped / max(res.plans + skipped, 1), "fr": fr,
            "ci": (cap * lo * rate, cap * hi * rate), "avg_pos": avg_pos,
            "dd_usd": abs(e["max_dd"]) * cap}


def sim_contrib(bins, start: float, add: float, horizon: float, n: int = 20_000, seed: int = 41, shift: float = 0.0):
    """Trade-level simulation with an extra deposit of `add` at each anniversary. bins: list of (fractions, rate) for equity <50, 50-100, 100+."""
    rng = np.random.default_rng(seed)
    K = 80
    cur = np.full(n, float(start))
    tprev = np.zeros(n)
    T, E = np.empty((n, K)), np.empty((n, K))
    rates = np.array([b[1] for b in bins])
    for k in range(K):
        b = np.where(cur < 50, 0, np.where(cur < 100, 1, 2))
        tnew = tprev + rng.exponential(1.0, size=n) / rates[b]
        cur = cur + add * (np.floor(np.minimum(tnew, horizon + 1)) - np.floor(np.minimum(tprev, horizon + 1)))
        b = np.where(cur < 50, 0, np.where(cur < 100, 1, 2))
        r = np.empty(n)
        for j, (fr, _) in enumerate(bins):
            m = b == j
            if m.any():
                r[m] = rng.choice(fr, size=int(m.sum())) - shift * fr.mean()
        cur = cur * (1 + r)
        T[:, k], E[:, k], tprev = tnew, cur, tnew
    return T, E


def state(T, E, start, add, t):
    k = (T <= t).sum(axis=1) - 1
    last_t = np.where(k >= 0, T[np.arange(len(T)), np.maximum(k, 0)], 0.0)
    eq = np.where(k >= 0, E[np.arange(len(E)), np.maximum(k, 0)], float(start))
    eq = eq + add * (np.floor(t) - np.floor(last_t))
    contributed = start + add * np.floor(t)
    return eq, eq - contributed


def usd(x: float) -> str:
    return f"{'+' if x >= 0 else '-'}${abs(x):,.0f}"


def build_report() -> str:
    base, universe = load_rules(), load_universe()
    btc, macro = load_data()
    feat = build_features(btc, macro, base)
    rb, rh = ladder(base)[2][1], ladder(base)[4][1]
    years = (feat.index[-1] - feat.index[0]).days / 365.25
    SB = {c: static_row(feat, rb, universe, c) for c in CAPS}
    SH = {c: static_row(feat, rh, universe, c) for c in CAPS}

    L = [f"# Capital efficiency of frozen v2 ({date.today()})", "",
         "Frozen v2, BTC spot only, no trade forced, risk per trade never raised: v2's own schedule (2% below 50 USDT, 1% from 50 up). "
         f"History {feat.index[0].date()} to {feat.index[-1].date()} ({years:.1f} years). **Half-edge** means the average trade's edge is "
         "halved (the audit found the edge thin and partly flattered); **harsh** uses the harsh fill model. Dollar yardsticks of $10, $50 "
         "and $100 a month are references only; what is meaningful to you is your call.", "",
         "Context: you currently have $25 allocated to the project, the ceiling is $300, additions are exceptional (at most $100 in any single "
         "year). The paper experiment runs at $300 to learn from forward results; the table below shows what each capital level would "
         "actually have done.", ""]

    L += ["## 1. What each capital level would have produced (base fills)", "",
          "Profit per year is the average over the whole history at that starting capital. Trades per year, fees and slippage are totals "
          "divided by years. Drawdown in dollars is the deepest peak-to-trough fall in account value. 'Setups skipped' is the share of "
          "valid v2 setups that could not be traded because the position would fall below Binance's minimum order (5.5 USDT with v2's buffer).", ""]
    rows = []
    for c in CAPS:
        s, e = SB[c], SB[c]["e"]
        h = SH[c]["e"]
        rows.append([f"${c}", f"${e['profit_per_year']:+.2f}", f"${e['profit_per_year'] / 2:+.2f}", f"${h['profit_per_year']:+.2f}",
                     f"${e['avg_month']:+.2f}", f"{s['rate']:.1f}", f"{e['fees'] / years:.2f} / {e['slippage'] / years:.2f}",
                     f"${s['dd_usd']:.0f} ({e['max_dd']:.1%})", f"{e['utilization']:.0%}", f"{s['skip']:.0%}", f"${s['avg_pos']:.0f}",
                     f"${s['ci'][0]:+.1f} to ${s['ci'][1]:+.1f}"])
    L += table(["Capital", "Profit / year", "Half-edge / year", "Harsh / year", "Average month", "Trades / year", "Fees / slippage per year ($)",
                "Max drawdown", "Capital in use (avg)", "Setups skipped (min order)", "Typical position", "95% range of profit / year (edge uncertainty)"], rows)
    r300 = SB[300]["e"]["cagr"]
    L += [f"Return on capital is about {r300:.1%} a year at $300 and does not rise with more capital: profit scales with capital because risk per "
          "trade is a fixed percentage of the account. The one real exception is the small account. At $25, v2 runs at 2% risk and cannot trade "
          f"{SB[25]['skip']:.0%} of its setups; at $50 it falls back to 1% risk and still skips {SB[50]['skip']:.0%}; from about $100 up "
          f"almost every setup is tradable ({SB[100]['skip']:.0%} skipped). That is a tradability effect, not an income effect.", ""]

    # marginal value of capital
    L += ["## 2. What would another $100 of capital add?", ""]
    rows = []
    for a, b in ((25, 125), (100, 200), (300, 400), (400, 500)):
        pa, pb = SB[a]["e"]["profit_per_year"], SB[b]["e"]["profit_per_year"]
        ha, hb = SH[a]["e"]["profit_per_year"], SH[b]["e"]["profit_per_year"]
        rows.append([f"${a} to ${b}", f"${pa:+.2f} to ${pb:+.2f}", f"${pb - pa:+.2f}", f"${(pb - pa) / 2:+.2f}", f"${hb - ha:+.2f}",
                     f"{100 / (pb - pa):.0f} years" if pb > pa else "never", f"${SB[b]['dd_usd'] - SB[a]['dd_usd']:+.0f}"])
    L += table(["Change", "Profit per year", "Extra profit per year (base)", "Half-edge", "Harsh", "Years of extra profit to repay the extra $100 (base)",
                "Extra drawdown in dollars"], rows)

    # reference incomes
    L += ["## 3. Capital needed for reference incomes at v2's return on capital", ""]
    rows = []
    for name, income in REFERENCE.items():
        rows.append([name, f"${income:,.0f}", f"${income / r300:,.0f}", f"${income / (r300 / 2):,.0f}",
                     f"${income / (SH[300]['e']['cagr']):,.0f}"])
    L += table(["Income yardstick", "Per year", "Capital needed (base)", "Capital needed (half-edge)", "Capital needed (harsh)"], rows)
    L += ["Capital that does not exist in your situation: even $700 (the most you could reach by 2030 with $300 plus $100 a year) is a small fraction "
          "of these.", ""]

    # contributions by 2030
    bins_b = [(SB[c]["fr"], SB[c]["rate"]) for c in BINS]
    bins_h = [(SH[c]["fr"], SH[c]["rate"]) for c in BINS]
    L += ["## 4. Research horizon 2030, with annual additions", "",
          "Trade-level simulation (20,000 paths) of the observed trade results, trades arriving at v2's observed rate for each capital band, "
          "plus an extra deposit on each anniversary of 2026-10-02 (first on 2027-10-02). Additions are **not** profit: all profit figures are "
          "trading P&L = final account value minus start minus everything deposited. No circuit breaker, so it ignores v2's pauses. Horizons: "
          "end of 2029 = 3.25 years, end of 2030 = 4.25 years.", ""]
    sims = {}
    for scen, bins, shift in (("base", bins_b, 0.0), ("half-edge", bins_b, 0.5), ("harsh", bins_h, 0.0)):
        for sc in START_CAPS:
            for add in ADDITIONS:
                sims[(scen, sc, add)] = sim_contrib(bins, sc, add, 4.25, seed=41 + sc + add, shift=shift)
    for hname, H in HORIZONS.items():
        L += [f"### By the {hname}", ""]
        rows = []
        for sc in START_CAPS:
            for add in ADDITIONS:
                put_in = sc + add * np.floor(H)
                cells = []
                for scen in ("base", "half-edge", "harsh"):
                    T, E = sims[(scen, sc, add)]
                    eq, pnl = state(T, E, sc, add, H)
                    lo, md, hi = np.percentile(pnl, [5, 50, 95])
                    cells.append(f"${md:+.0f} (${lo:+.0f} to ${hi:+.0f})")
                T, E = sims[("base", sc, add)]
                eq, pnl = state(T, E, sc, add, H)
                _, pnl_prev = state(T, E, sc, add, H - 1)
                final_year = pnl - pnl_prev
                T2, E2 = sims[("half-edge", sc, add)]
                _, p2 = state(T2, E2, sc, add, H)
                _, p2p = state(T2, E2, sc, add, H - 1)
                rows.append([f"${sc}", f"+${add}/yr" if add else "none", f"${put_in:,.0f}", cells[0], cells[1], cells[2],
                             f"${np.median(final_year):+.1f}", f"${np.median(p2 - p2p):+.1f}", f"{(pnl < 0).mean():.0%}"])
        L += table(["Start", "Additions", "Total put in", "Trading profit, base: median (5th to 95th pct)", "Half-edge", "Harsh",
                    "Profit in the last 12 months, base median", "Half-edge median", "Chance of trading profit below zero (base)"], rows)

    # verdict inputs
    T, E = sims[("base", 300, 100)]
    _, pnl30 = state(T, E, 300, 100, 4.25)
    _, pnl29 = state(T, E, 300, 100, 3.25)
    _, prev = state(T, E, 300, 100, 3.25)
    best_final = np.median(state(T, E, 300, 100, 4.25)[1] - state(T, E, 300, 100, 3.25)[1])
    T0, E0 = sims[("base", 300, 0)]
    gain100 = np.median(pnl30) - np.median(state(T0, E0, 300, 0, 4.25)[1])
    L += ["## 5. Verdict", "",
          f"- **Is the strategy economically worth continuing at your capital?** As an income source, no. At $300 it produced about ${SB[300]['e']['profit_per_year']:.2f} a year "
          f"(${SB[300]['e']['profit_per_year'] / 2:.2f} if the edge is half, ${SH[300]['e']['profit_per_year']:.2f} with harsh fills), with a worst fall of about "
          f"${SB[300]['dd_usd']:.0f}. At $25 it produced about ${SB[25]['e']['profit_per_year']:.2f} a year and could not trade {SB[25]['skip']:.0%} of its setups. "
          "As a low-cost forward test of whether the historical edge is real, it is cheap: about $0.6 a year in fees at $300, and nothing is at risk in paper mode.",
          f"- **Would another $100 materially change the economics?** No. At v2's return on capital (about {r300:.1%} a year) an extra $100 adds roughly "
          f"${100 * r300:.0f} a year (about ${50 * r300:.1f} if the edge is half) and a few dollars more drawdown; it would take about {1 / r300:.0f} years of "
          "that extra profit to repay itself. The one practical benefit of capital is tradability: moving from $25 toward $100 removes the minimum-order "
          "skipping, but even that is worth only a couple of dollars a year. I do not recommend adding capital for the sake of the account growing slowly.",
          f"- **Can it become a meaningful income by 2030?** Not on this evidence. Even with $300 plus $100 every year (total $700 put in by 2030), the median "
          f"trading profit by the end of 2030 is about {usd(np.median(pnl30))} in total and about {usd(best_final)} in the final year in the base case; the "
          f"half-edge case is lower, and there is a real chance the profit is below zero (see the tables). Adding $100 a year raises the 2030 median profit by only "
          f"about {usd(gain100)} relative to adding nothing. A $10 a month yardstick ($120 a year) needs roughly ${REFERENCE['$10 a month'] / r300:,.0f} at this return.",
          "- **What this does not say:** it does not say the strategy is worthless as a controlled learning exercise, and it does not rule out that forward results "
          "differ from history. It says that no capital level inside your constraints turns this edge into income, and that raising risk to compensate was already "
          "rejected on probability of loss.", ""]
    return "\n".join(L)


def main() -> None:
    text = build_report()
    REPORTS_DIR.mkdir(exist_ok=True)
    path = REPORTS_DIR / f"capital_efficiency_{date.today()}.md"
    path.write_text(text, encoding="utf-8")
    print(f"Saved to {path} ({len(text.splitlines())} lines)")


if __name__ == "__main__":
    main()
