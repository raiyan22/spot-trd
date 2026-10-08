"""Pre-registered test of upgrade ideas from external research, each applied on top of the current rules.

Adoption rule (fixed before running): a variant is adopted only if its return/max-drawdown beats the baseline in
BOTH 2018-2022 and 2023-now, it keeps at least half the baseline's trades in each period, and the 25 USDT account's
max drawdown over the full period is no deeper than the baseline's.
"""
import copy
from datetime import date

from spot_trd.backtest import run_backtest
from spot_trd.config import REPORTS_DIR, load_rules, load_universe
from spot_trd.data import load_data, load_external
from spot_trd.regime import build_features
from spot_trd.report import fmt_pct, summarize
from spot_trd.research import SPLIT, evaluate

SOURCES = {
    "A": "Contrarian sentiment research (Crypto Fear & Greed Index, alternative.me)",
    "B": "Contrarian sentiment research (Crypto Fear & Greed Index, alternative.me)",
    "C": "Grobys, Näsman & Sandretto (2026), on-chain MVRV and Bitcoin cycles",
    "D": "Zarattini, Pagani & Barbon (2025), Catching Crypto Trends: Donchian-midpoint trailing stop",
    "E": "Zarattini, Pagani & Barbon (2025): multi-lookback Donchian ensemble",
}


def variants(base: dict) -> list[tuple[str, str, dict]]:
    def v(**changes):
        r = copy.deepcopy(base)
        for section, values in changes.items():
            r.setdefault(section, {})
            if isinstance(values, dict):
                r[section].update(values)
            else:
                r[section] = values
        return r

    return [
        ("0", "Baseline: current rules (v2)", copy.deepcopy(base)),
        ("A", "Skip entries when Fear & Greed >= 75", v(filters={"fng_block_at": 75})),
        ("B", "Enter only when Fear & Greed <= 50", v(filters={"fng_entry_max": 50})),
        ("C", "Skip entries when MVRV >= 3.0", v(filters={"mvrv_block_at": 3.0})),
        ("D", "Exit on 20-day Donchian-midpoint trail (not 2 ATR)",
         v(exit={"trail_mode": "donchian_mid", "donchian_lookback": 20})),
        ("E", "1D gate = Donchian ensemble (>= 3 of 20/60/150/250/360d)",
         v(regime={"ensemble": {"lookbacks": [20, 60, 150, 250, 360], "min_share": 0.6}})),
    ]


def mar(s: dict) -> float:
    return s["total_return"] / max(abs(s["max_drawdown"]), 0.01)


def main() -> None:
    base, universe = load_rules(), load_universe()
    btc, macro = load_data()
    ext = load_external()
    rows = []
    for key, name, rules in variants(base):
        feat = build_features(btc, macro, rules, ext=ext)
        ins = evaluate(feat[feat.index < SPLIT], rules, universe)
        oos = evaluate(feat[feat.index >= SPLIT], rules, universe)
        small = run_backtest(feat, rules, universe)
        sm = summarize(small.trades, small.equity, small.initial)
        rows.append((key, name, ins, oos, sm))

    _, _, b_is, b_oos, b_sm = rows[0]
    lines = [
        f"# Upgrade test ({date.today()})", "",
        "Five ideas from external research, each added to the current rules and judged by the adoption rule "
        "fixed before running: beat the baseline's return/max-drawdown in **both** 2018-2022 and 2023-now, keep "
        ">= half its trades in each period, and don't deepen the 25 USDT account's max drawdown.", "",
        "Edge test: 100,000 USDT at a flat 2% risk. Return/DD = total return / |max drawdown|.", "",
        "| # | Variant | 2018-22 trades | 2018-22 avg R | 2018-22 return / DD | 2023+ trades | 2023+ avg R | "
        "2023+ return / DD | 25 USDT full period | Verdict |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    adopted = []
    for key, name, ins, oos, sm in rows:
        if key == "0":
            verdict = "baseline"
        else:
            checks = {
                "better 2018-22": mar(ins) > mar(b_is),
                "better 2023+": mar(oos) > mar(b_oos),
                "enough trades": ins["trades"] >= b_is["trades"] / 2 and oos["trades"] >= b_oos["trades"] / 2,
                "small-account DD ok": sm["max_drawdown"] >= b_sm["max_drawdown"],
            }
            failed = [k for k, ok in checks.items() if not ok]
            verdict = "ADOPT" if not failed else "reject: " + ", ".join(f"not {k}" for k in failed)
            if not failed:
                adopted.append((key, name))
        lines.append(
            f"| {key} | {name} | {ins['trades']} | {ins['avg_R']:+.2f} | {fmt_pct(ins['total_return'])} / "
            f"{fmt_pct(ins['max_drawdown'])} ({mar(ins):.2f}) | {oos['trades']} | {oos['avg_R']:+.2f} | "
            f"{fmt_pct(oos['total_return'])} / {fmt_pct(oos['max_drawdown'])} ({mar(oos):.2f}) | "
            f"{sm['final_equity']:.2f} USDT, DD {fmt_pct(sm['max_drawdown'])} | {verdict} |")
    lines += ["", "## Sources", ""] + [f"- {k}: {s}" for k, s in SOURCES.items()]
    lines += ["", "## Result", ""]
    lines.append("Adopted: " + ", ".join(f"{k} ({n})" for k, n in adopted) if adopted else
                 "No variant passed. The current rules stay unchanged.")
    text = "\n".join(lines)
    REPORTS_DIR.mkdir(exist_ok=True)
    path = REPORTS_DIR / f"upgrades_{date.today()}.md"
    path.write_text(text, encoding="utf-8")
    print(text)
    print(f"\nSaved to {path}")


if __name__ == "__main__":
    main()
