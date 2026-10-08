"""Execution comparison for FROZEN v2 signals: current ladder vs market at next open vs one limit (diagnostic, analysis only).

Pre-registration: reports/limit_entry_preregistration_2026-10-02.md, written and hashed before any result existed.
A manual limit buy before a v2 card issues a plan is a different strategy and is not evaluated here.
Run: uv run python -m spot_trd.limit_entry
"""
import hashlib
import json
from datetime import date

import numpy as np
import pandas as pd

from spot_trd.audit import economics, ladder, pct, table
from spot_trd.backtest import Result, run_portfolio
from spot_trd.config import REPORTS_DIR, ROOT, load_rules, load_universe
from spot_trd.data import load_data
from spot_trd.regime import build_features

SPLIT = pd.Timestamp("2023-01-01")
EDGE_CAPITAL, EDGE_RISK = 100_000.0, 0.02
METHODS = {"M0": ("ladder", "M0 current v2 ladder (2 limits)"), "M1": ("market", "M1 market at next open"),
           "M2": ("single_limit", "M2 one limit at close - 0.5 ATR")}
MIN_GAIN_R, MIN_FILL, MAX_DD_WORSE = 0.10, 0.70, 0.02


def run(feat, rules, universe, mode, capital=EDGE_CAPITAL, risk=EDGE_RISK) -> Result:
    return run_portfolio({"BTC/USDT": feat}, rules, universe, capital, risk, entry_mode=mode)


def per_plan(res: Result) -> pd.DataFrame:
    """One row per plan issued: the trade's R if it filled, else 0 (a missed trade earns nothing)."""
    by = {t.plan_date: t for t in res.trades}
    rows = [{"date": d, "R": by[d].r_multiple if d in by else 0.0, "filled": d in by} for d in res.plan_dates]
    return pd.DataFrame(rows)


def stats(res: Result, feat: pd.DataFrame) -> dict:
    e = economics(res)
    pp = per_plan(res)
    imp = []
    for t in res.trades:
        sig_i = feat.index.get_loc(t.plan_date)
        if sig_i + 1 < len(feat):
            imp.append(1 - t.avg_entry / feat["open"].iloc[sig_i + 1])
    return {"plans": len(pp), "fill": float(pp["filled"].mean()), "trades": e["trades"], "win": e["win_rate"],
            "R_filled": e["avg_R"], "R_signal": float(pp["R"].mean()), "improve": float(np.mean(imp)) if imp else float("nan"),
            "fees": e["fees"], "ret": e["total_return"], "dd": e["max_dd"],
            "calmar": e["cagr"] / abs(e["max_dd"]) if e["max_dd"] < 0 else float("nan"), "pp": pp, "e": e}


def month_bootstrap(a: pd.DataFrame, b: pd.DataFrame, n: int = 10_000, seed: int = 8) -> float:
    """2.5th percentile of mean(R per plan) of a minus b, resampling calendar months of the plan date (paired by month)."""
    ma = a.assign(m=a["date"].dt.to_period("M")).groupby("m")["R"].agg(["sum", "count"])
    mb = b.assign(m=b["date"].dt.to_period("M")).groupby("m")["R"].agg(["sum", "count"])
    months = ma.index.union(mb.index)
    sa, ca = ma["sum"].reindex(months, fill_value=0).to_numpy(), ma["count"].reindex(months, fill_value=0).to_numpy()
    sb, cb = mb["sum"].reindex(months, fill_value=0).to_numpy(), mb["count"].reindex(months, fill_value=0).to_numpy()
    idx = np.random.default_rng(seed).integers(0, len(months), size=(n, len(months)))
    d = sa[idx].sum(axis=1) / np.maximum(ca[idx].sum(axis=1), 1) - sb[idx].sum(axis=1) / np.maximum(cb[idx].sum(axis=1), 1)
    return float(np.percentile(d, 2.5))


def half_mean(pp: pd.DataFrame, lo, hi) -> float:
    m = pd.Series(True, index=pp.index)
    if lo is not None:
        m &= pp["date"] >= lo
    if hi is not None:
        m &= pp["date"] < hi
    return float(pp.loc[m, "R"].mean())


def build_report() -> str:
    base, universe = load_rules(), load_universe()
    btc, macro = load_data()
    feat = build_features(btc, macro, base)
    rb, rh = ladder(base)[2][1], ladder(base)[4][1]
    freeze = json.loads((ROOT / "reports" / "limit_entry_freeze_2026-10-02.json").read_text(encoding="utf-8"))
    changed = [f for f, d in freeze["sha256"].items() if hashlib.sha256((ROOT / f).read_bytes()).hexdigest() != d]

    S = {k: {"base": stats(run(feat, rb, universe, m), feat), "harsh": stats(run(feat, rh, universe, m), feat)}
         for k, (m, _) in METHODS.items()}
    L = [f"# Execution comparison for frozen v2 signals ({date.today()})", "",
         f"Pre-registration: `limit_entry_preregistration_2026-10-02.md` (frozen {freeze['frozen_at_utc']}); frozen files unchanged: "
         f"**{'YES' if not changed else 'NO ' + str(changed)}**. Analysis only; v2 is untouched. **A manual limit buy before a v2 card issues a "
         "plan changes the signal and is not evaluated; the default stays: no manual limit buy, wait for the frozen v2 signal.** Large "
         f"account (100,000 USDT at 2% risk) so the minimum order does not distort; {feat.index[0].date()} to {feat.index[-1].date()}.", "",
         "Plans issued: " + ", ".join(f"{k} {S[k]['base']['plans']}" for k in METHODS) + ". Every method reads the same signal column from the "
         "frozen feature code; the counts differ only because a method that is already in a position, or that filled sooner or later, is flat on "
         "different days.", ""]

    L += ["## 1. Results, base fills", ""]
    rows = []
    for k, (_, lab) in METHODS.items():
        s = S[k]["base"]
        rows.append([lab, s["plans"], f"{s['fill']:.0%}", s["trades"], f"{s['win']:.0%}", f"{s['R_filled']:+.3f}", f"{s['R_signal']:+.3f}",
                     pct(s["improve"]), f"{s['fees']:,.0f}", pct(s["ret"]), pct(s["dd"]), f"{s['calmar']:.2f}"])
    L += table(["Method", "Plans", "Fill rate", "Trades", "Win rate", "Mean R per filled trade", "Mean R per signal (non-fill = 0)",
                "Entry vs next open (price improvement)", "Fees ($)", "Total return", "Max DD", "Calmar"], rows)
    L += ["Harsh fills:", ""]
    rows = []
    for k, (_, lab) in METHODS.items():
        s = S[k]["harsh"]
        rows.append([lab, s["plans"], f"{s['fill']:.0%}", s["trades"], f"{s['R_filled']:+.3f}", f"{s['R_signal']:+.3f}", pct(s["ret"]),
                     pct(s["dd"]), f"{s['calmar']:.2f}"])
    L += table(["Method", "Plans", "Fill rate", "Trades", "Mean R per filled trade", "Mean R per signal", "Total return", "Max DD", "Calmar"], rows)

    m1_by_date = {t.plan_date: t.r_multiple for t in run(feat, rb, universe, "market").trades}
    L += ["## 2. Opportunity cost of missed trades", ""]
    rows = []
    for k in ("M0", "M2"):
        res = run(feat, rb, universe, METHODS[k][0])
        filled = {t.plan_date for t in res.trades}
        missed = [d for d in res.plan_dates if d not in filled]
        r_missed = [m1_by_date[d] for d in missed if d in m1_by_date]
        rows.append([METHODS[k][1], len(missed), f"{len(missed) / max(len(res.plan_dates), 1):.0%}", len(r_missed),
                     f"{np.mean(r_missed):+.2f}R" if r_missed else "n/a", f"{np.sum(r_missed):+.1f}R" if r_missed else "n/a"])
    L += table(["Method", "Plans that never filled", "Share of plans", "Of those, signals a market entry also traded",
                "Their mean R under market entry", "Their total R"], rows)
    L += ["The R a missed plan would have earned is approximated by the market-entry run's trade for the same signal date; account states "
          "differ between runs, so treat it as indicative.", ""]

    L += ["## 3. The $300 account (v2's risk schedule), base fills", ""]
    rows = []
    for k, (m, lab) in METHODS.items():
        e = economics(run(feat, rb, universe, m, 300.0, None))
        rows.append([lab, f"{e['final']:.2f}", f"${e['profit_per_year']:+.2f}", e["trades"], f"{e['max_dd']:.1%}", f"{e['fees'] / e['years']:.2f}"])
    L += table(["Method", "Final capital", "Profit per year", "Trades", "Max DD", "Fees per year ($)"], rows)

    L += ["## 4. Pre-registered test (alternatives vs M0, large account)", ""]
    outcomes, promising = [], []
    a0 = S["M0"]["base"]
    for k in ("M1", "M2"):
        b, h = S[k]["base"], S[k]["harsh"]
        gain = b["R_signal"] - a0["R_signal"]
        lb = month_bootstrap(b["pp"], a0["pp"])
        halves = [half_mean(b["pp"], lo, hi) - half_mean(a0["pp"], lo, hi) for lo, hi in ((None, SPLIT), (SPLIT, None))]
        g = {
            "E1 gain >= 0.10R per signal and bootstrap lower bound > 0": (gain >= MIN_GAIN_R and lb > 0, f"{gain:+.3f}R, lower bound {lb:+.3f}"),
            "E2 Calmar >= M0 (base and harsh)": (b["calmar"] >= a0["calmar"] and h["calmar"] >= S["M0"]["harsh"]["calmar"],
                                                f"{b['calmar']:.2f} vs {a0['calmar']:.2f}; harsh {h['calmar']:.2f} vs {S['M0']['harsh']['calmar']:.2f}"),
            "E3 max DD no more than 2 points worse": (b["dd"] >= a0["dd"] - MAX_DD_WORSE, f"{b['dd']:.1%} vs {a0['dd']:.1%}"),
            "E4 difference not negative in either half": (all(x >= 0 for x in halves), f"{halves[0]:+.3f} / {halves[1]:+.3f}"),
            "E5 fill rate >= 70%": (b["fill"] >= MIN_FILL, f"{b['fill']:.0%}"),
        }
        ok = all(v[0] for v in g.values())
        if ok:
            promising.append(k)
        outcomes.append((k, g, ok))
    gates = list(outcomes[0][1])
    L += table(["Test"] + [METHODS[k][1] for k, _, _ in outcomes],
               [[gt] + [("PASS " if g[gt][0] else "**FAIL** ") + g[gt][1] for _, g, _ in outcomes] for gt in gates] +
               [["**Outcome**"] + ["**WORTH A SEPARATE PRE-REGISTRATION**" if ok else "**NO CHANGE: keep M0**" for _, _, ok in outcomes]])

    L += ["## 5. Answer", "",
          "- **Default: no manual limit buy. Wait for the frozen v2 signal.** When a card says BUY, place the plan's own two limit orders; "
          "that already is a limit-entry method.",
          ("- Alternatives that passed every pre-registered test: " + ", ".join(METHODS[k][1] for k in promising) +
           ". This does not change anything live: it only means a separate, stricter pre-registration could be written if you approve that phase.")
          if promising else "- No alternative passed the pre-registered tests, so there is nothing to carry forward and no change to propose."]
    return "\n".join(L)


def main() -> None:
    text = build_report()
    REPORTS_DIR.mkdir(exist_ok=True)
    path = REPORTS_DIR / f"limit_entry_{date.today()}.md"
    path.write_text(text, encoding="utf-8")
    print(f"Saved to {path} ({len(text.splitlines())} lines)")


if __name__ == "__main__":
    main()
