"""Shadow book: what every buy plan would have done if you had placed it exactly as the card said, next to what you did.

Each plan in the journal is replayed with the backtest engine's own per-bar logic (limit fills need a 0.05% trade-through,
stop first within a bar, 2-ATR chandelier trail, trend exit at the next open), using the card's own order sizes, on
completed daily candles only. Nothing here changes the frozen v2 rules: it is bookkeeping, not research.

A plan that appeared only because you were out of the market while the follower would still have been in an earlier
trade is marked 'overlap' and left out of the follower's total (a follower would never have got that card).

Run: uv run spot shadow
"""
import argparse
from dataclasses import dataclass, field

import pandas as pd

from spot_trd.backtest import EXECUTION_DEFAULTS, Result, _Account, _Asset
from spot_trd.clock import local
from spot_trd.config import JOURNAL_PATH, PAPER_JOURNAL_PATH, load_rules
from spot_trd.journal import Book, TradeRecord, load_book, utcnow
from spot_trd.sizing import Order
from spot_trd.strategy import Plan


@dataclass
class Shadow:
    trade_id: str
    signal_date: pd.Timestamp
    valid_until: pd.Timestamp
    status: str                    # waiting | unfilled | open | closed | no data
    qty: float = 0.0
    avg_entry: float = 0.0
    entry_date: pd.Timestamp | None = None
    exit_date: pd.Timestamp | None = None
    exit_reason: str = ""
    pnl: float = 0.0               # realized if closed, marked to the last close (after the sell fee) if open
    stop_now: float = 0.0
    overlap: bool = False
    fills: list = field(default_factory=list)


def simulate(trade: TradeRecord, feat: pd.DataFrame, rules: dict) -> Shadow:
    """Replay one plan bar by bar from the day after its signal close, as if both limit orders were placed on time."""
    p = trade.plan
    sig, valid_until = pd.Timestamp(p["signal_date"]), pd.Timestamp(p["valid_until"])
    out = Shadow(trade.trade_id, sig, valid_until, "no data")
    if sig not in feat.index:
        return out
    i0 = feat.index.get_loc(sig)
    orders = [Order(price, qty) for price, qty in p["orders"]]
    valid_days = max(int((valid_until - (sig + pd.Timedelta(days=1))).days), 1)
    plan = Plan(sig, orders, False, p["stop"], None, None, p.get("risk_usdt", 0.0), valid_days)
    acct = _Account(1e9, rules["risk"])  # cash is never the constraint: the card's own sizes are replayed
    a = _Asset(rules["market"]["symbol"], feat, rules, feat.index)
    acct.assets.append(a)
    a.plan, a.pending, a.expiry_i = plan, list(orders), i0 + valid_days
    res = Result(acct.cash, [], pd.Series(dtype=float), pd.Series(dtype=bool))
    x = {**EXECUTION_DEFAULTS, **rules.get("execution", {})}
    last_i = i0
    for i in range(i0 + 1, len(feat)):
        before = a.qty
        a.process(i, acct, res, x)
        last_i = i
        if a.qty > before:
            out.fills.append(feat.index[i])
        if res.trades:
            break
    fee = rules["market"]["fee_rate"]
    if res.trades:
        t = res.trades[0]
        out.status, out.qty, out.avg_entry = "closed", t.qty, t.avg_entry
        out.entry_date, out.exit_date, out.exit_reason = t.entry_date, t.exit_date, t.exit_reason
        out.pnl, out.stop_now = t.pnl, t.stop_level
    elif a.pos is not None:
        out.status, out.qty, out.avg_entry = "open", a.pos.qty_bought, a.pos.cost / a.pos.qty_bought
        out.entry_date, out.stop_now = a.pos.entry_date, a.pos.stop
        out.pnl = a.qty * feat["close"].iloc[last_i] * (1 - fee) - a.pos.cost
        if a.pos.exit_next:
            out.exit_reason = f"{a.pos.exit_next} exit at the next open"
    else:
        out.status = "waiting" if last_i < i0 + valid_days else "unfilled"
    return out


def what_you_did(t: TradeRecord, now: pd.Timestamp) -> str:
    planned = sum(q for _, q in t.plan["orders"])
    if t.btc_bought > 0:
        part = "" if t.btc_bought >= planned * 0.95 else f" (part: {t.btc_bought:.5f} of {planned:.5f} BTC)"
        return ("placed, closed" if t.closed_at is not None else "placed, holding") + part
    if t.skipped:
        return "skipped (you said so)"
    if now < pd.Timestamp(t.plan["valid_until"]):
        return "no fill reported yet"
    return "no fill reported"


def actual_pnl(t: TradeRecord, close: float, rules: dict) -> float:
    if t.btc_bought == 0:
        return 0.0
    return t.proceeds + t.held * close * (1 - rules["market"]["fee_rate"]) - t.cost


def build(book: Book, feat: pd.DataFrame, rules: dict) -> list[Shadow]:
    rows, busy_until = [], pd.Timestamp.min
    for t in book.trades.values():
        s = simulate(t, feat, rules)
        if s.signal_date < busy_until:
            s.overlap = True
        elif s.status in ("open", "waiting"):
            busy_until = pd.Timestamp.max
        elif s.status == "closed":
            busy_until = s.exit_date
        rows.append(s)
    return rows


def totals(book: Book, rows: list[Shadow], close: float, rules: dict) -> tuple[float, float]:
    follower = sum(s.pnl for s in rows if not s.overlap)
    actual = sum(actual_pnl(t, close, rules) for t in book.trades.values())
    return follower, actual


def card_lines(book: Book, feat: pd.DataFrame, rules: dict) -> list[str]:
    """Two or three lines for the daily card. Empty until the first plan exists."""
    if not book.trades:
        return []
    rows = build(book, feat, rules)
    close = float(feat["close"].iloc[-1])
    follower, actual = totals(book, rows, close, rules)
    first = min(s.signal_date for s in rows)
    gap = actual - follower
    lines = [f"SHADOW BOOK (plans since {(first + pd.Timedelta(days=1)).date()}): followed every card {follower:+.2f} USDT | "
             f"what you did {actual:+.2f} USDT | difference {gap:+.2f} USDT"]
    last = rows[-1]
    t = book.trades[last.trade_id]
    lines.append(f"  Latest {last.trade_id}. You: {what_you_did(t, utcnow())}. Following the card: {describe(last)}")
    lines.append("  Small samples prove nothing either way; details: `uv run spot shadow`.")
    return lines


def describe(s: Shadow) -> str:
    if s.status == "no data":
        return "not replayed yet (needs the next daily candle)"
    if s.status == "waiting":
        return f"no fill yet (orders valid until {local(s.valid_until)})"
    if s.status == "unfilled":
        return "orders would not have filled; nothing gained or lost"
    filled = ", ".join(str(d.date()) for d in s.fills)
    if s.status == "open":
        tail = f"; {s.exit_reason}" if s.exit_reason else ""
        return (f"bought {s.qty:.5f} BTC at avg {s.avg_entry:,.2f} ({filled}), still open, {s.pnl:+.2f} USDT now, "
                f"stop {s.stop_now:,.2f}{tail}")
    return (f"bought {s.qty:.5f} BTC at avg {s.avg_entry:,.2f}, sold {s.exit_date.date()} ({s.exit_reason}), "
            f"{s.pnl:+.2f} USDT")


def report(book: Book, feat: pd.DataFrame, rules: dict) -> str:
    if not book.trades:
        return "Shadow book: no buy plans yet. It starts with the first card that says PLACE."
    rows = build(book, feat, rules)
    close = float(feat["close"].iloc[-1])
    follower, actual = totals(book, rows, close, rules)
    now = utcnow()
    lines = [f"SHADOW BOOK: every buy plan as if placed exactly as the card said, vs what you did "
             f"(daily close {feat.index[-1].date()}, BTC {close:,.2f})", ""]
    for s in rows:
        t = book.trades[s.trade_id]
        lines.append(f"{s.trade_id}  card {(s.signal_date + pd.Timedelta(days=1)).date()}"
                     + ("  [overlap: a follower would still have been in the earlier trade]" if s.overlap else ""))
        lines.append(f"  Following the card: {describe(s)}")
        lines.append(f"  You: {what_you_did(t, now)}, {actual_pnl(t, close, rules):+.2f} USDT")
    gap = actual - follower
    verdict = ("you are ahead of the card" if gap > 0.005 else "the card is ahead of you" if gap < -0.005 else "no difference yet")
    lines += ["", f"Followed every card: {follower:+.2f} USDT.  What you did: {actual:+.2f} USDT.  "
                  f"Difference {gap:+.2f} USDT ({verdict}).",
              "Open trades are marked to the last daily close. Fills use the backtest's pessimistic model, so a real",
              "fill can differ by a few cents. With this few trades the gap is mostly luck; it says nothing yet about",
              "whether the rules have an edge, and the rules stay frozen whatever it shows."]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="What following every card would have done, vs what you did.")
    ap.add_argument("--paper", action="store_true")
    ap.add_argument("--no-refresh", action="store_true")
    args = ap.parse_args(argv)
    from spot_trd.data import load_data
    from spot_trd.regime import build_features

    rules = load_rules()
    book = load_book(rules, PAPER_JOURNAL_PATH if args.paper else JOURNAL_PATH)
    btc, macro = load_data(refresh=not args.no_refresh)
    print(report(book, build_features(btc, macro, rules), rules))


if __name__ == "__main__":
    main()
