"""Append-only trading journal. Account state is rebuilt by replaying events, never stored separately."""
import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from spot_trd.config import JOURNAL_PATH, PAPER_JOURNAL_PATH, load_rules, load_universe
from spot_trd.halal_guard import HalalViolation, check_order
from spot_trd.risk import CircuitBreaker

FIELDS = ["time_utc", "event", "trade_id", "btc", "usdt", "fee_usdt", "details", "note"]


def utcnow() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC").tz_localize(None).floor("s")


@dataclass
class TradeRecord:
    trade_id: str
    plan: dict
    planned_at: pd.Timestamp
    btc_bought: float = 0.0
    btc_sold: float = 0.0
    cost: float = 0.0
    proceeds: float = 0.0
    first_buy: pd.Timestamp | None = None
    closed_at: pd.Timestamp | None = None
    cancelled: bool = False

    @property
    def held(self) -> float:
        return self.btc_bought - self.btc_sold

    @property
    def avg_entry(self) -> float:
        return self.cost / self.btc_bought

    @property
    def pnl(self) -> float:
        return self.proceeds - self.cost

    def risk_usdt(self, rules: dict) -> float:
        fee, slip = rules["market"]["fee_rate"], rules["exit"]["stop_slippage"]
        return self.cost - self.btc_bought * self.plan["stop"] * (1 - slip) * (1 - fee)


@dataclass
class Book:
    rules: dict
    cash: float = 0.0
    deposited: float = 0.0
    trades: dict[str, TradeRecord] | None = None
    breaker: CircuitBreaker | None = None

    @property
    def open_trade(self) -> TradeRecord | None:
        return next((t for t in self.trades.values() if t.first_buy and t.closed_at is None), None)

    def active_plan(self, now: pd.Timestamp) -> TradeRecord | None:
        """Latest plan whose limit orders may still be resting on the exchange."""
        for t in reversed(list(self.trades.values())):
            if t.cancelled or t.closed_at is not None:
                continue
            if now < pd.Timestamp(t.plan["valid_until"]):
                return t
        return None

    @property
    def closed_trades(self) -> list[TradeRecord]:
        return [t for t in self.trades.values() if t.closed_at is not None]

    def next_trade_id(self) -> str:
        return f"T{len(self.trades) + 1:03d}"


def read_events(path: Path = JOURNAL_PATH) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def append_event(path: Path = JOURNAL_PATH, **row) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    row.setdefault("time_utc", utcnow().isoformat())
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in FIELDS})


def _num(v: str) -> float:
    return float(v) if v not in ("", None) else 0.0


def load_book(rules: dict, path: Path = JOURNAL_PATH) -> Book:
    book = Book(rules, trades={})
    dust = rules["market"]["qty_step"]
    for e in read_events(path):
        when = pd.Timestamp(e["time_utc"])
        kind, tid = e["event"], e["trade_id"]
        btc, usdt, fee = _num(e["btc"]), _num(e["usdt"]), _num(e["fee_usdt"])
        if kind == "deposit":
            book.cash += usdt
            book.deposited += usdt
            if book.breaker is None:
                book.breaker = CircuitBreaker(rules["risk"], book.cash)
            else:
                book.breaker.on_deposit(book.cash)
        elif kind == "plan":
            book.trades[tid] = TradeRecord(tid, json.loads(e["details"]), when)
        elif kind == "buy":
            t = book.trades[tid]
            t.btc_bought += btc
            t.cost += usdt + fee
            t.first_buy = t.first_buy or when
            book.cash -= usdt + fee
        elif kind == "sell":
            t = book.trades[tid]
            t.btc_sold += btc
            t.proceeds += usdt - fee
            book.cash += usdt - fee
            if t.held < dust:
                t.closed_at = when
                book.breaker.on_trade_closed(when, t.pnl, book.cash)
        elif kind == "cancel":
            book.trades[tid].cancelled = True
    return book


def record_plan(plan, rules: dict, path: Path = JOURNAL_PATH, trade_id: str | None = None,
                valid_until: pd.Timestamp | None = None) -> str:
    tid = trade_id or load_book(rules, path).next_trade_id()
    details = {
        "orders": [[o.price, o.qty] for o in plan.orders],
        "stop": plan.stop,
        "risk_usdt": plan.risk_usdt,
        "valid_until": valid_until.isoformat(),
        "signal_date": str(plan.date.date()),
        "rules_version": rules["version"],
        "strategy": rules["strategy"],
    }
    append_event(path, event="plan", trade_id=tid, details=json.dumps(details))
    return tid


def _target_trade(book: Book, trade_id: str | None, now: pd.Timestamp) -> TradeRecord:
    if trade_id:
        return book.trades[trade_id]
    t = book.open_trade or book.active_plan(now)
    if t is None:
        raise SystemExit("No open trade or active plan. Only buy what a trade card tells you to buy.")
    return t


def status_text(book: Book) -> str:
    lines = [f"Cash: {book.cash:.2f} USDT (deposited {book.deposited:.2f})"]
    t = book.open_trade
    if t:
        lines.append(f"Open {t.trade_id}: {t.held:.5f} BTC, avg entry {t.avg_entry:,.2f}, stop at entry "
                     f"{t.plan['stop']:,.2f}. Run the trade card for today's stop.")
    closed = book.closed_trades
    if closed:
        r = [c.pnl / c.risk_usdt(book.rules) for c in closed]
        wins = sum(c.pnl > 0 for c in closed)
        lines.append(f"Closed trades: {len(closed)}, wins {wins}, total P&L {sum(c.pnl for c in closed):+.2f} USDT, "
                     f"avg {sum(r) / len(r):+.2f}R")
        for c, rr in zip(closed, r):
            lines.append(f"  {c.trade_id} {c.first_buy.date()} -> {c.closed_at.date()}: {c.pnl:+.2f} USDT ({rr:+.2f}R)")
    if book.breaker and book.breaker.events:
        lines.append("Circuit-breaker events:")
        lines += [f"  {d.date()}: {msg}" for d, msg in book.breaker.events]
    return "\n".join(lines)


def main(argv: list[str] | None = None, path: Path | None = None) -> None:
    ap = argparse.ArgumentParser(description="Log what actually happened on Binance.")
    ap.add_argument("--paper", action="store_true", help="use the paper-trading journal")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("deposit", help="add starting capital (USDT)")
    d.add_argument("usdt", type=float)
    for name, helptext in (("buy", "a limit buy filled"), ("sell", "you sold BTC (stop, trail or exit)")):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("--usdt", type=float, required=True,
                       help="USDT spent (buy) or received (sell), as Binance's order 'Total' shows")
        p.add_argument("--btc", type=float, required=True,
                       help="BTC received (buy, after any BTC fee) or sold (sell)")
        p.add_argument("--fee-usdt", type=float, default=0.0, help="fee paid in BNB, valued in USDT")
        p.add_argument("--trade", help="trade id; defaults to the open trade or active plan")
        p.add_argument("--time", help="fill time in UTC (ISO); defaults to now")
        p.add_argument("--note", default="")
    c = sub.add_parser("cancel", help="you cancelled a plan's unfilled orders")
    c.add_argument("--trade")
    n = sub.add_parser("note", help="free-text note (mistakes, emotions, deviations)")
    n.add_argument("text")
    sub.add_parser("status", help="show account state")
    args = ap.parse_args(argv)
    path = path or (PAPER_JOURNAL_PATH if args.paper else JOURNAL_PATH)

    rules, universe = load_rules(), load_universe()
    book = load_book(rules, path)
    now = utcnow()

    if args.cmd == "deposit":
        append_event(path, event="deposit", usdt=args.usdt)
    elif args.cmd in ("buy", "sell"):
        if book.breaker is None:
            raise SystemExit("Log your starting capital first: journal deposit 25")
        t = _target_trade(book, args.trade, pd.Timestamp(args.time) if args.time else now)  # plan active at fill time
        try:
            check_order(rules["market"]["symbol"], "spot", args.cmd, args.btc, t.held, universe)
        except HalalViolation as err:
            raise SystemExit(f"Rejected: {err}")
        if args.cmd == "buy" and args.usdt + args.fee_usdt > book.cash + 1e-9:
            raise SystemExit(f"Rejected: buy of {args.usdt:.2f} USDT exceeds cash {book.cash:.2f}. Spot only, no borrowing.")
        append_event(path, event=args.cmd, trade_id=t.trade_id, btc=args.btc, usdt=args.usdt,
                     fee_usdt=args.fee_usdt, note=args.note,
                     time_utc=pd.Timestamp(args.time).isoformat() if args.time else now.isoformat())
        print(f"Logged {args.cmd} for {t.trade_id} at ~{args.usdt / args.btc:,.2f} USDT/BTC")
    elif args.cmd == "cancel":
        t = book.trades[args.trade] if args.trade else book.active_plan(now)
        if t is None:
            raise SystemExit("No active plan to cancel.")
        append_event(path, event="cancel", trade_id=t.trade_id)
    elif args.cmd == "note":
        append_event(path, event="note", note=args.text)
    print(status_text(load_book(rules, path)))


if __name__ == "__main__":
    main()
