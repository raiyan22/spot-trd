"""Walk-forward comparison of rule variants: select on 2018-2022, then check on 2023-now."""
import copy
import itertools
from datetime import date

import pandas as pd

from spot_trd.backtest import run_backtest
from spot_trd.config import REPORTS_DIR, load_rules, load_universe
from spot_trd.data import load_data
from spot_trd.regime import build_features
from spot_trd.report import fmt_pct, summarize

SPLIT = pd.Timestamp("2023-01-01")
EDGE_CAPITAL, EDGE_RISK = 100_000.0, 0.02
MIN_TRADES = 10
MAX_IS_DRAWDOWN = 0.10  # capital preservation comes first: deeper in-sample drawdowns are ineligible


def candidates(base: dict) -> list[tuple[str, dict]]:
    out = [("current rules (rules.yaml)", copy.deepcopy(base))]
    for stop, trail, tp1 in itertools.product((1.0, 1.5), (2.0, 3.0, 4.0), (1.5, None)):
        r = copy.deepcopy(base)
        r["strategy"] = "pullback"
        r["exit"].update(stop_atr_mult=stop, trail_atr_mult=trail, tp1_r=tp1, tp2_r=None,
                         max_hold_days=None, regime_exit=True)
        out.append((f"pullback stop {stop} ATR, trail {trail} ATR, TP1 {tp1 or 'off'}", r))
    for days, mult in itertools.product((20, 50), (2.0, 3.0, 4.0, 5.0)):
        r = copy.deepcopy(base)
        r["strategy"] = "trend"
        r["setup"]["breakout_days"] = days
        r["exit"].update(stop_atr_mult=mult, trail_atr_mult=mult, tp1_r=None, tp2_r=None,
                         max_hold_days=None, regime_exit=True)
        out.append((f"trend {days}d breakout, stop/trail {mult} ATR", r))
    return out


def score(s: dict) -> float:
    if s["trades"] < MIN_TRADES or s["max_drawdown"] < -MAX_IS_DRAWDOWN:
        return float("-inf")
    return s["total_return"] / max(abs(s["max_drawdown"]), 0.01)


def evaluate(feat: pd.DataFrame, rules: dict, universe: dict) -> dict:
    res = run_backtest(feat, rules, universe, EDGE_CAPITAL, EDGE_RISK)
    s = summarize(res.trades, res.equity, res.initial)
    s["exposure"] = res.in_market.mean()
    return s


def main() -> None:
    base, universe = load_rules(), load_universe()
    btc, macro = load_data()
    rows = []
    for name, rules in candidates(base):
        feat = build_features(btc, macro, rules)
        ins = evaluate(feat[feat.index < SPLIT], rules, universe)
        oos = evaluate(feat[feat.index >= SPLIT], rules, universe)
        rows.append((name, rules, ins, oos))
    rows.sort(key=lambda x: score(x[2]), reverse=True)

    def cells(s: dict) -> str:
        return (f"{s['trades']} | {fmt_pct(s['win_rate']).lstrip('+')} | {s['avg_R']:+.2f} | "
                f"{fmt_pct(s['total_return'])} | {fmt_pct(s['max_drawdown'])} | {s['exposure']:.0%}")

    lines = [
        f"# Rule research ({date.today()})",
        "",
        f"Each variant starts with {EDGE_CAPITAL:,.0f} USDT at a flat {EDGE_RISK:.0%} risk, so Binance's minimum "
        "order doesn't distort the edge. Variants are ranked by **in-sample (2018-2022) return / max drawdown** "
        f"with at least {MIN_TRADES} trades and an in-sample max drawdown within {MAX_IS_DRAWDOWN:.0%} "
        "(variants breaking either limit rank last). The 2023-now columns were not used for ranking.",
        "",
        "| Rank | Variant | IS trades | IS win | IS avg R | IS return | IS max DD | IS exposure "
        "| OOS trades | OOS win | OOS avg R | OOS return | OOS max DD | OOS exposure |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for rank, (name, _, ins, oos) in enumerate(rows, 1):
        lines.append(f"| {rank} | {name} | {cells(ins)} | {cells(oos)} |")

    best_name, best_rules, _, _ = rows[0]
    feat = build_features(btc, macro, best_rules)
    small = run_backtest(feat, best_rules, universe)
    s = summarize(small.trades, small.equity, small.initial)
    lines += [
        "",
        f"## Selected: {best_name}",
        "",
        f"Your account, full period ({feat.index[0].date()} to {feat.index[-1].date()}), 25 USDT with the "
        f"2%-under-50-USDT risk schedule: final {s['final_equity']:.2f} USDT ({fmt_pct(s['total_return'])}), "
        f"max drawdown {fmt_pct(s['max_drawdown'])}, {s['trades']} trades, win rate "
        f"{fmt_pct(s['win_rate']).lstrip('+')}, avg R {s['avg_R']:+.2f}, halts {len(small.halts)}, "
        f"setups skipped for minimum order size {sum(small.skipped.values())}.",
        "",
        "Selected exit settings: " + ", ".join(f"{k}={v}" for k, v in best_rules["exit"].items()),
        f"Strategy: {best_rules['strategy']}, breakout_days={best_rules['setup']['breakout_days']}",
    ]
    text = "\n".join(lines)
    REPORTS_DIR.mkdir(exist_ok=True)
    path = REPORTS_DIR / f"research_{date.today()}.md"
    path.write_text(text, encoding="utf-8")
    print(text)
    print(f"\nSaved to {path}")


if __name__ == "__main__":
    main()
