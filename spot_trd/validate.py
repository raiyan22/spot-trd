"""Validation layer: is the data sound, and is the system performing the way its backtest says it should?"""
import argparse
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from spot_trd.backtest import run_backtest
from spot_trd.config import (JOURNAL_PATH, PAPER_JOURNAL_PATH, REPORTS_DIR, load_events, load_rules,
                             load_universe)
from spot_trd.data import load_data, market_limits
from spot_trd.journal import Book, load_book, utcnow
from spot_trd.regime import build_features

ORDER = {"PASS": 0, "INFO": 0, "WARN": 1, "FAIL": 2}
KEY_COLUMNS = ["close", "atr", "ema_slow", "rsi", "trend_ok", "regime_ok", "signal"]


@dataclass
class Check:
    name: str
    status: str
    detail: str


def data_checks(btc: pd.DataFrame, macro: pd.DataFrame, feat: pd.DataFrame, events: dict,
                now: pd.Timestamp) -> list[Check]:
    out = []
    expected = now.normalize() - pd.Timedelta(days=1)
    last = btc.index[-1]
    if last >= expected:
        out.append(Check("BTC data fresh", "PASS", f"last daily close {last.date()}"))
    else:
        out.append(Check("BTC data fresh", "FAIL", f"last daily close {last.date()}, expected {expected.date()}. "
                                                   "Decisions would use old prices. Run without --no-refresh."))
    lag = (now.normalize() - macro.dropna(how="all").index[-1]).days
    out.append(Check("Macro data fresh", "PASS" if lag <= 4 else "WARN",
                     f"latest macro row is {lag} day(s) old (weekends and US holidays allow up to 4)"))
    missing = [c for c in KEY_COLUMNS if pd.isna(feat.iloc[-1][c])]
    out.append(Check("Latest features complete", "FAIL" if missing else "PASS",
                     f"missing: {missing}" if missing else "all decision inputs present"))
    move = btc["close"].iloc[-1] / btc["close"].iloc[-2] - 1
    out.append(Check("Price sanity", "WARN" if abs(move) > 0.25 else "PASS",
                     f"last daily move {move:+.1%}" + (" (check for a bad tick)" if abs(move) > 0.25 else "")))
    dates = [pd.Timestamp(d) for k in ("fomc_decisions", "cpi_releases") for d in events.get(k, [])]
    horizon = now + pd.Timedelta(days=60)
    cpi_last = max(pd.Timestamp(d) for d in events.get("cpi_releases", []))
    ok = max(dates) >= horizon and cpi_last >= horizon
    out.append(Check("Event calendar coverage", "PASS" if ok else "WARN",
                     f"FOMC/CPI dates known through {cpi_last.date()} (CPI)" +
                     ("" if ok else ": add the next year's dates to config/events.yaml")))
    return out


def exchange_check(rules: dict) -> Check:
    mkt = rules["market"]
    try:
        live = market_limits(mkt["symbol"])
    except Exception as err:  # network or exchange outage shouldn't crash validation
        return Check("Binance limits match config", "WARN", f"could not reach Binance: {err}")
    diffs = [f"{k}: config {mkt[c]} vs Binance {live[k]}"
             for k, c in (("min_notional", "min_notional"), ("qty_step", "qty_step"), ("taker_fee", "fee_rate"))
             if live[k] is not None and abs(float(live[k]) - float(mkt[c])) > 1e-12]
    if live["type"] != "spot":
        diffs.append(f"market type is {live['type']}, not spot")
    return Check("Binance limits match config", "FAIL" if diffs else "PASS",
                 "; ".join(diffs) or "min order, lot step and fee unchanged")


def bootstrap_band(values: np.ndarray, n: int, stat=np.mean, draws: int = 10_000, seed: int = 7) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return stat(rng.choice(values, size=(draws, n), replace=True), axis=1)


def performance_checks(book: Book, bt_r: np.ndarray, bt_max_dd: float, rules: dict) -> list[Check]:
    closed = book.closed_trades
    n = len(closed)
    if n == 0:
        return [Check("Live vs backtest", "INFO", "no closed trades yet; checks start after the first exit")]
    r = np.array([t.pnl / t.risk_usdt(rules) for t in closed])
    out = []

    means = bootstrap_band(bt_r, n)
    pct = (means < r.mean()).mean()
    status = "FAIL" if pct < 0.05 else "WARN" if pct < 0.25 else "PASS"
    out.append(Check("Expectancy vs backtest", status,
                     f"live avg {r.mean():+.2f}R over {n} trades; backtest says {n} trades average between "
                     f"{np.percentile(means, 5):+.2f}R and {np.percentile(means, 95):+.2f}R 90% of the time "
                     f"(live sits at the {pct:.0%} percentile)" +
                     (". Worse than 95% of backtest outcomes: stop and review." if status == "FAIL" else "")))

    wins = bootstrap_band((bt_r > 0).astype(float), n)
    wpct = (wins < (r > 0).mean()).mean()
    out.append(Check("Win rate vs backtest", "WARN" if wpct < 0.05 else "PASS",
                     f"live {(r > 0).mean():.0%}; backtest 90% range for {n} trades "
                     f"{np.percentile(wins, 5):.0%} to {np.percentile(wins, 95):.0%}"))

    worst = r.min()
    out.append(Check("Loss per trade capped at 1R", "FAIL" if worst < -1.25 else "PASS",
                     f"worst trade {worst:+.2f}R" + (" (stop not respected or a big gap: review execution)"
                                                     if worst < -1.25 else "")))

    equity = book.deposited + np.cumsum([t.pnl for t in closed])
    curve = np.concatenate([[book.deposited], equity])
    dd = (curve / np.maximum.accumulate(curve) - 1).min()
    out.append(Check("Drawdown within backtest worst", "FAIL" if dd < bt_max_dd else "PASS",
                     f"live max drawdown {dd:.1%}; backtest worst {bt_max_dd:.1%}"))
    return out


def decay_check(feat: pd.DataFrame, rules: dict, universe: dict) -> tuple[Check, np.ndarray, float]:
    res = run_backtest(feat, rules, universe, 100_000.0, 0.02)
    r = np.array([t.r_multiple for t in res.trades])
    cutoff = feat.index[-1] - pd.Timedelta(days=365)
    recent = np.array([t.r_multiple for t in res.trades if t.exit_date >= cutoff])
    small = run_backtest(feat, rules, universe)
    max_dd = (small.equity / small.equity.cummax() - 1).min()
    if len(recent) < 5:
        chk = Check("Recent 12 months (backtest)", "INFO", f"only {len(recent)} trades in the last year; too few to judge")
    else:
        status = "WARN" if recent.mean() < 0 else "PASS"
        chk = Check("Recent 12 months (backtest)", status,
                    f"{len(recent)} trades, avg {recent.mean():+.2f}R vs {r.mean():+.2f}R over the full history")
    return chk, r, max_dd


def scorecard(checks: list[Check]) -> str:
    worst = max(checks, key=lambda c: ORDER[c.status]).status
    verdict = {"PASS": "System healthy", "INFO": "System healthy",
               "WARN": "Usable, but read the warnings", "FAIL": "Do NOT trade until the failures are fixed"}[worst]
    lines = [f"# Validation ({date.today()}): {worst}: {verdict}", "", "| Check | Status | Detail |", "|---|---|---|"]
    lines += [f"| {c.name} | {c.status} | {c.detail} |" for c in checks]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate data health and live performance against the backtest.")
    ap.add_argument("--paper", action="store_true", help="validate the paper-trading journal")
    ap.add_argument("--no-refresh", action="store_true")
    ap.add_argument("--offline", action="store_true", help="skip the Binance limits check")
    args = ap.parse_args()

    rules, universe, events = load_rules(), load_universe(), load_events()
    btc, macro = load_data(refresh=not args.no_refresh)
    feat = build_features(btc, macro, rules)
    now = utcnow()
    checks = data_checks(btc, macro, feat, events, now)
    if not args.offline:
        checks.append(exchange_check(rules))
    decay, bt_r, bt_dd = decay_check(feat, rules, universe)
    checks.append(decay)
    book = load_book(rules, PAPER_JOURNAL_PATH if args.paper else JOURNAL_PATH)
    checks += performance_checks(book, bt_r, bt_dd, rules)

    text = scorecard(checks)
    REPORTS_DIR.mkdir(exist_ok=True)
    path = REPORTS_DIR / f"validation_{date.today()}.md"
    path.write_text(text, encoding="utf-8")
    print(text)
    print(f"\nSaved to {path}")


if __name__ == "__main__":
    main()
