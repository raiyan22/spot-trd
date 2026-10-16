"""Structured log of every daily decision and its inputs, plus an outcome analysis to find which rules help or hurt."""
import argparse
import csv
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from spot_trd.config import JOURNAL_PATH, PAPER_JOURNAL_PATH, REPORTS_DIR, ROOT, load_rules
from spot_trd.data import load_data
from spot_trd.journal import load_book, utcnow
from spot_trd.regime import build_features

LOG_LIVE = ROOT / "journal" / "decisions.csv"
LOG_PAPER = ROOT / "journal" / "decisions_paper.csv"
INPUTS = ["close", "ema_pb", "ema_fast", "ema_slow", "rsi", "atr", "monthly_up", "daily_up", "risk_off", "spx_weak",
          "dxy_surge", "commodity_stress", "regime_ok", "pullback", "signal"]
FIELDS = ["card_day", "close_date", "logged_at", "rules_version", "kind", "reason", "headline", "trade_id",
          *INPUTS]
BIG_MOVE = 0.05  # a 10-day move this size counts as a missed rally / avoided drop


def log_path(paper: bool) -> Path:
    return LOG_PAPER if paper else LOG_LIVE


def reason_code(headline: str, last: pd.Series) -> str:
    """Why the system decided what it did, in a form that can be grouped and counted."""
    if headline.startswith("PLACE"):
        return "buy_plan"
    if headline.startswith(("HOLD", "KEEP", "SELL", "CHECK")):
        return headline.split()[0].strip(".").lower()
    if "paused" in headline:
        return "circuit_breaker"
    if "You skipped" in headline:
        return "user_skipped"
    if not last["regime_ok"]:
        blocked = [name for name, ok in (("monthly", last["monthly_up"]), ("daily", last["daily_up"]),
                                         ("macro", not last["risk_off"])) if not ok]
        return "gate:" + "+".join(blocked)
    if "skipped because" in headline:
        return "event_window"
    if "too small" in headline:
        return "min_order_size"
    return "no_pullback"


def _value(v) -> bool | float:
    return bool(v) if isinstance(v, (bool, np.bool_)) else round(float(v), 4)


def record_decision(feat: pd.DataFrame, headline: str, trade_id: str | None, rules: dict, paper: bool) -> None:
    """Append one row per card day; later runs on the same day don't duplicate it."""
    from spot_trd.dashboard import decision_kind

    last = feat.iloc[-1]
    card_day = str((last.name + pd.Timedelta(days=1)).date())
    path = log_path(paper)
    if path.exists():
        with open(path, newline="", encoding="utf-8") as f:
            if any(r["card_day"] == card_day for r in csv.DictReader(f)):
                return
    row = {
        "card_day": card_day, "close_date": str(last.name.date()), "logged_at": utcnow().isoformat(),
        "rules_version": rules["version"], "kind": decision_kind(headline), "reason": reason_code(headline, last),
        "headline": headline, "trade_id": trade_id or "",
        **{k: _value(last[k]) for k in INPUTS},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)


def outcome_label(kind: str, fwd10: float | None) -> str:
    if fwd10 is None or pd.isna(fwd10):
        return "pending (needs 10 more days)"
    if kind == "neutral":
        if fwd10 >= BIG_MOVE:
            return "missed rally"
        if fwd10 <= -BIG_MOVE:
            return "avoided drop"
        return "quiet (no big move)"
    return "in market / acting"


def analyze(log: pd.DataFrame, close: pd.Series, book) -> str:
    log = log.copy()
    log["close_date"] = pd.to_datetime(log["close_date"])
    for h in (5, 10, 20):
        fwd = close.shift(-h) / close - 1
        log[f"fwd{h}"] = log["close_date"].map(fwd)
    log["outcome"] = [outcome_label(k, f) for k, f in zip(log["kind"], log["fwd10"])]

    pct = lambda x: "n/a" if pd.isna(x) else f"{x:+.1%}"
    lines = [f"# Decision review ({date.today()})", "",
             f"{len(log)} daily decisions logged, {log['card_day'].min()} to {log['card_day'].max()}. "
             f"Outcomes compare the decision-day close with BTC 5/10/20 days later. "
             f"A 10-day move of at least {BIG_MOVE:.0%} counts as a big move.", "",
             "## What the system decided, and what BTC did next", "",
             "| Decision | Days | Avg 10d BTC move | BTC up after 10d |", "|---|---|---|---|"]
    for kind, g in log.groupby("kind"):
        done = g["fwd10"].dropna()
        if len(done):
            lines.append(f"| {kind} | {len(g)} | {pct(done.mean())} | {(done > 0).mean():.0%} |")
        else:
            lines.append(f"| {kind} | {len(g)} | pending | pending |")

    neutral = log[log["kind"] == "neutral"]
    lines += ["", "## Staying out: which rule was responsible", "",
              "| Reason | Days | Missed rallies | Avoided drops | Avg 10d move after |", "|---|---|---|---|---|"]
    for reason, g in neutral.groupby("reason"):
        lines.append(f"| {reason} | {len(g)} | {(g['outcome'] == 'missed rally').sum()} | "
                     f"{(g['outcome'] == 'avoided drop').sum()} | {pct(g['fwd10'].mean())} |")

    closed = {t.trade_id: t for t in book.closed_trades} if book else {}
    plans = log[log["reason"] == "buy_plan"]
    lines += ["", "## Buy decisions and their results", ""]
    if plans.empty:
        lines.append("No buy plans yet.")
    else:
        lines += ["| Day | Trade | Filled? | Result | BTC 10d after |", "|---|---|---|---|---|"]
        for _, p in plans.iterrows():
            t = book.trades.get(p["trade_id"]) if book else None
            filled = "yes" if t is not None and t.btc_bought > 0 else "no (expired/cancelled)"
            result = (f"{closed[p['trade_id']].pnl:+.2f} USDT ({closed[p['trade_id']].pnl / closed[p['trade_id']].risk_usdt(book.rules):+.2f}R)"
                      if p["trade_id"] in closed else ("open" if filled == "yes" else "-"))
            lines.append(f"| {p['card_day']} | {p['trade_id']} | {filled} | {result} | {pct(p['fwd10'])} |")

    misses = neutral[neutral["outcome"] == "missed rally"]
    lines += ["", "## Missed rallies to examine", ""]
    if misses.empty:
        lines.append("None so far.")
    else:
        lines += ["| Day | Reason | Close | RSI | 10d after | 20d after |", "|---|---|---|---|---|---|"]
        lines += [f"| {r['card_day']} | {r['reason']} | {float(r['close']):,.0f} | {float(r['rsi']):.0f} | "
                  f"{pct(r['fwd10'])} | {pct(r['fwd20'])} |" for _, r in misses.iterrows()]
    lines += ["", "How to read this: a rule that blocks many rallies but few drops is costing money; a rule that "
              "blocks many drops is earning its place. Judge a rule only after dozens of days, and confirm any change "
              "with `spot research` / `spot upgrades` on full history before adopting it."]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Evaluate logged daily decisions against what BTC did next.")
    ap.add_argument("--paper", action="store_true")
    args = ap.parse_args()
    path = log_path(args.paper)
    if not path.exists():
        raise SystemExit("No decisions logged yet. They're recorded by `spot today` and by the monitor each day.")
    rules = load_rules()
    btc, macro = load_data()
    close = build_features(btc, macro, rules)["close"]
    book = load_book(rules, PAPER_JOURNAL_PATH if args.paper else JOURNAL_PATH)
    text = analyze(pd.read_csv(path), close, book)
    REPORTS_DIR.mkdir(exist_ok=True)
    out = REPORTS_DIR / f"decisions_{'paper_' if args.paper else ''}{date.today()}.md"
    out.write_text(text, encoding="utf-8")
    print(text)
    print(f"\nSaved to {out}")


if __name__ == "__main__":
    main()
