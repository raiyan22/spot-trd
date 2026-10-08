import argparse
from datetime import date

import pandas as pd

from spot_trd.backtest import Result, run_backtest
from spot_trd.config import REPORTS_DIR, load_rules, load_universe
from spot_trd.data import load_data
from spot_trd.patterns import current_analogs, regime_table
from spot_trd.regime import build_features

SPLIT = pd.Timestamp("2023-01-01")


def max_drawdown(equity: pd.Series) -> float:
    return (equity / equity.cummax() - 1).min()


def summarize(trades: list, equity: pd.Series, initial: float) -> dict:
    pnl = pd.Series([t.pnl for t in trades], dtype=float)
    r = pd.Series([t.r_multiple for t in trades], dtype=float)
    gains, losses = pnl[pnl > 0].sum(), -pnl[pnl < 0].sum()
    years = (equity.index[-1] - equity.index[0]).days / 365.25
    final = equity.iloc[-1]
    return {
        "trades": len(trades),
        "win_rate": (pnl > 0).mean() if len(pnl) else float("nan"),
        "avg_R": r.mean(),
        "median_R": r.median(),
        "profit_factor": gains / losses if losses > 0 else float("inf"),
        "total_return": final / initial - 1,
        "cagr": (final / initial) ** (1 / years) - 1 if years > 0 and final > 0 else float("nan"),
        "max_drawdown": max_drawdown(equity),
        "final_equity": final,
    }


def fmt_pct(x: float) -> str:
    return "n/a" if pd.isna(x) else f"{x:+.1%}"


def result_section(title: str, res: Result, risk_label: str) -> list[str]:
    s = summarize(res.trades, res.equity, res.initial)
    exits = pd.Series([t.exit_reason for t in res.trades]).value_counts().to_dict()
    lines = [
        f"### {title}",
        f"Start {res.initial:,.2f} USDT, risk {risk_label}, "
        f"{res.equity.index[0].date()} to {res.equity.index[-1].date()}",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Final equity | {s['final_equity']:,.2f} USDT ({fmt_pct(s['total_return'])}) |",
        f"| CAGR | {fmt_pct(s['cagr'])} |",
        f"| Max drawdown | {fmt_pct(s['max_drawdown'])} |",
        f"| Trades | {s['trades']} (plans {res.plans}, unfilled {res.unfilled}) |",
        f"| Win rate | {fmt_pct(s['win_rate']).lstrip('+')} |",
        f"| Avg R / median R | {s['avg_R']:+.2f} / {s['median_R']:+.2f} |",
        f"| Profit factor | {s['profit_factor']:.2f} |",
        f"| Time in market | {res.in_market.mean():.1%} |",
        f"| Exits | {', '.join(f'{k} {v}' for k, v in exits.items()) or 'none'} |",
        f"| Setups skipped | {', '.join(f'{k}: {v}' for k, v in res.skipped.items()) or 'none'} |",
        f"| Circuit-breaker halts | {len(res.halts)} |",
        "",
    ]
    if res.trades:
        lines += ["Early vs recent period (no parameters were tuned on either):", "",
                  "| Period | Trades | Win rate | Avg R | Return | Max DD |", "|---|---|---|---|---|---|"]
        for name, lo, hi in (("2018-2022", None, SPLIT), ("2023-now", SPLIT, None)):
            eq = res.equity
            if lo is not None:
                eq = eq[eq.index >= lo]
            if hi is not None:
                eq = eq[eq.index < hi]
            ts = [t for t in res.trades if (lo is None or t.exit_date >= lo) and (hi is None or t.exit_date < hi)]
            p = summarize(ts, eq, eq.iloc[0])
            lines.append(f"| {name} | {p['trades']} | {fmt_pct(p['win_rate']).lstrip('+')} | "
                         f"{p['avg_R']:+.2f} | {fmt_pct(p['total_return'])} | {fmt_pct(p['max_drawdown'])} |")
        lines += ["", "Per year:", "", "| Year | Trades | Sum R | Return |", "|---|---|---|---|"]
        year_end = res.equity.groupby(res.equity.index.year).last()
        year_ret = year_end / year_end.shift(1, fill_value=res.initial) - 1
        for yr, ret in year_ret.items():
            ts = [t for t in res.trades if t.exit_date.year == yr]
            lines.append(f"| {yr} | {len(ts)} | {sum(t.r_multiple for t in ts):+.2f} | {fmt_pct(ret)} |")
        lines.append("")
    if res.halts:
        lines += ["Halts:", ""] + [f"- {d.date()}: {why}" for d, why in res.halts] + [""]
    return lines


def stats_table(df: pd.DataFrame) -> list[str]:
    out = ["| Horizon | Days | Mean | Median | % up | Worst 10% |", "|---|---|---|---|---|---|"]
    for h, r in df.iterrows():
        out.append(f"| {h} | {int(r['days'])} | {fmt_pct(r['mean'])} | {fmt_pct(r['median'])} | "
                   f"{r['pct_up']:.0%} | {fmt_pct(r['worst_10pct'])} |")
    return out


def build_report(refresh: bool) -> str:
    rules, universe = load_rules(), load_universe()
    btc, macro = load_data(refresh)
    feat = build_features(btc, macro, rules)
    last = feat.iloc[-1]

    bh = feat["close"] / feat["close"].iloc[0]
    lines = [
        f"# Backtest report: rules v{rules['version']} ({date.today()})",
        "",
        f"Data: BTC/USDT daily (Binance) {feat.index[0].date()} to {feat.index[-1].date()}; "
        "S&P 500, gold, oil, DXY (yfinance).",
        "",
        "## Current regime (latest daily close)",
        "",
        f"- BTC close {last['close']:,.2f} | EMA20 {last['ema_pb']:,.0f} | EMA50 {last['ema_fast']:,.0f} | "
        f"EMA200 {last['ema_slow']:,.0f} | RSI {last['rsi']:.0f} | ATR {last['atr']:,.0f} "
        f"({last['atr'] / last['close']:.1%})",
        f"- 1M uptrend: {last['monthly_up']} | 1D uptrend: {last['daily_up']} | "
        f"Macro risk-off: {last['risk_off']} (S&P weak {last['spx_weak']}, DXY surge {last['dxy_surge']}, "
        f"commodity stress {last['commodity_stress']})",
        f"- Regime gate: {'PASS' if last['regime_ok'] else 'BLOCKED'} | Pullback setup today: {last['setup']}",
        "",
    ]
    sig, analogs = current_analogs(feat)
    lines += [f"Historical days with the same signature {sig}:", ""] + stats_table(analogs) + [""]

    lines += ["## Forward BTC returns by regime (2018-now)", ""]
    for name, df in regime_table(feat).items():
        lines += [f"**{name}**", ""] + stats_table(df) + [""]

    lines += [
        "## Strategy backtests",
        "",
        f"Buy & hold BTC over the same period: {fmt_pct(bh.iloc[-1] - 1)}, max drawdown {fmt_pct(max_drawdown(bh))}.",
        "",
    ]
    runs = [
        ("A. Edge test (large capital, minimum order size irrelevant)", 100_000.0, 0.02, "2% per trade"),
        ("B. Your account: 25 USDT with the risk schedule", 25.0, None, "2% per trade under 50 USDT, then 1%"),
    ]
    for title, cap, rp, label in runs:
        lines += result_section(title, run_backtest(feat, rules, universe, cap, rp), label)
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Backtest the halal BTC spot strategy and write a report.")
    ap.add_argument("--refresh", action="store_true", help="re-download market data")
    args = ap.parse_args()
    text = build_report(args.refresh)
    REPORTS_DIR.mkdir(exist_ok=True)
    path = REPORTS_DIR / f"backtest_{date.today()}.md"
    path.write_text(text, encoding="utf-8")
    print(text)
    print(f"\nSaved to {path}")


if __name__ == "__main__":
    main()
