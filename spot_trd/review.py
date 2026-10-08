"""Post-mortem of closed trades: what happened, whether the plan was followed, and what to learn."""
import argparse
from collections import Counter
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from spot_trd.config import JOURNAL_PATH, PAPER_JOURNAL_PATH, ROOT, load_rules
from spot_trd.data import load_data
from spot_trd.journal import Book, TradeRecord, load_book, read_events
from spot_trd.regime import build_features
from spot_trd.run import trailing_stop

REVIEWS_DIR = ROOT / "journal" / "reviews"
TOLERANCE = 0.002

LESSONS = {
    "chased entry": "Only use the card's limit prices. A fill above plan means buying strength the system didn't ask for.",
    "late stop": "Place the stop order the moment a buy fills, and move it every day. A late or missing stop turns 1R into more.",
    "discretionary exit": "The card said HOLD. Early exits cut the big winners this strategy depends on (most profit comes from a few trades).",
    "late regime exit": "When the card says SELL because the trend broke, sell that day. Hoping for a bounce is how 1R becomes 3R.",
}


@dataclass
class TradeReview:
    trade: TradeRecord
    r: float
    days: int
    exit_price: float
    stop_at_exit: float
    exit_type: str
    mistakes: list[str] = field(default_factory=list)


def review_trade(t: TradeRecord, feat: pd.DataFrame, rules: dict) -> TradeReview:
    fee = rules["market"]["fee_rate"]
    exit_day = t.closed_at.normalize()
    stop, _ = trailing_stop(feat[feat.index < exit_day], t, rules)
    exit_price = t.proceeds / t.btc_sold / (1 - fee)
    rv = TradeReview(t, t.pnl / t.risk_usdt(rules), (t.closed_at - t.first_buy).days, exit_price, stop, "")

    planned_max = max(p for p, _ in t.plan["orders"])
    if t.avg_entry / (1 + fee) > planned_max * (1 + TOLERANCE):
        rv.mistakes.append("chased entry")

    after = feat[(feat.index >= t.first_buy.normalize()) & (feat.index < exit_day)]
    broke = after.index[~after["trend_ok"].to_numpy()]
    offset = rules["exit"]["stop_limit_offset"]
    if exit_price <= stop * (1 + TOLERANCE):
        rv.exit_type = "stop"
        if exit_price < stop * (1 - offset - TOLERANCE):
            rv.mistakes.append("late stop")
    elif len(broke):
        rv.exit_type = "regime exit"
        if (exit_day - broke[0]).days > 1:
            rv.mistakes.append("late regime exit")
    else:
        rv.exit_type = "manual"
        rv.mistakes.append("discretionary exit")
    if len(broke) and rv.exit_type == "stop" and (exit_day - broke[0]).days > 1:
        rv.mistakes.append("late regime exit")
    return rv


def build_review(book: Book, feat: pd.DataFrame, rules: dict, notes: list[dict]) -> str:
    reviews = [review_trade(t, feat, rules) for t in book.closed_trades]
    lines = [f"# Journal review ({date.today()})", ""]
    if not reviews:
        return "\n".join(lines + ["No closed trades yet."])

    r = pd.Series([x.r for x in reviews])
    pnl = pd.Series([x.trade.pnl for x in reviews])
    wins, losses = r[r > 0], r[r <= 0]
    clean = sum(not x.mistakes for x in reviews)
    equity = book.deposited + pnl.cumsum()
    curve = pd.concat([pd.Series([book.deposited]), equity], ignore_index=True)
    lines += [
        "## Scoreboard", "",
        "| Metric | Value |", "|---|---|",
        f"| Closed trades | {len(reviews)} |",
        f"| Win rate | {(r > 0).mean():.0%} |",
        f"| Expectancy | {r.mean():+.2f}R per trade |",
        f"| Avg win / avg loss | {wins.mean() if len(wins) else 0:+.2f}R / {losses.mean() if len(losses) else 0:+.2f}R |",
        f"| Profit factor | {pnl[pnl > 0].sum() / -pnl[pnl < 0].sum() if (pnl < 0).any() else float('inf'):.2f} |",
        f"| Total P&L | {pnl.sum():+.2f} USDT ({pnl.sum() / book.deposited:+.1%}) |",
        f"| Max drawdown (closed trades) | {(curve / curve.cummax() - 1).min():.1%} |",
        f"| Plan adherence | {clean}/{len(reviews)} trades with no execution mistakes |",
        "", "## Trades", "",
        "| Trade | Entry | Exit | Days | Avg entry | Exit price | Stop then | Exit type | P&L | R | Mistakes |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for x in reviews:
        t = x.trade
        lines.append(f"| {t.trade_id} | {t.first_buy.date()} | {t.closed_at.date()} | {x.days} | {t.avg_entry:,.0f} | "
                     f"{x.exit_price:,.0f} | {x.stop_at_exit:,.0f} | {x.exit_type} | {t.pnl:+.2f} | {x.r:+.2f} | "
                     f"{', '.join(x.mistakes) or 'none'} |")

    counts = Counter(m for x in reviews for m in x.mistakes)
    lines += ["", "## What to learn", ""]
    if counts:
        lines += [f"- **{m}** ({n}x): {LESSONS[m]}" for m, n in counts.most_common()]
    else:
        lines.append("- Execution matched the plan on every trade. Any losses were the strategy's normal cost, "
                     "not mistakes. Judge the strategy itself with `spot_trd.validate`.")
    big = [x for x in reviews if x.r < -1.25]
    if big:
        lines.append(f"- {len(big)} trade(s) lost more than 1.25R. The 1R cap only holds if the stop is always live.")
    if notes:
        lines += ["", "## Your notes", ""] + [f"- {n['time_utc'][:10]}: {n['note']}" for n in notes]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Review closed trades for mistakes and lessons.")
    ap.add_argument("--paper", action="store_true", help="review the paper-trading journal")
    ap.add_argument("--no-refresh", action="store_true")
    args = ap.parse_args()
    rules = load_rules()
    path = PAPER_JOURNAL_PATH if args.paper else JOURNAL_PATH
    btc, macro = load_data(refresh=not args.no_refresh)
    feat = build_features(btc, macro, rules)
    notes = [e for e in read_events(path) if e["event"] == "note"]
    text = build_review(load_book(rules, path), feat, rules, notes)
    REVIEWS_DIR.mkdir(parents=True, exist_ok=True)
    out = REVIEWS_DIR / f"review_{'paper_' if args.paper else ''}{date.today()}.md"
    out.write_text(text, encoding="utf-8")
    print(text)
    print(f"\nSaved to {out}")


if __name__ == "__main__":
    main()
