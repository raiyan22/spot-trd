"""Daily trade card: run once after each 00:00 UTC daily close."""
import argparse

import pandas as pd

from spot_trd.clock import daily_close, local, local_hm
from spot_trd.config import JOURNAL_PATH, PAPER_JOURNAL_PATH, load_events, load_rules, load_universe
from spot_trd.data import load_data
from spot_trd.decisions import record_decision
from spot_trd.journal import Book, TradeRecord, load_book, record_plan, status_text, utcnow
from spot_trd.patterns import analog_stats, forward_returns
from spot_trd.regime import build_features
from spot_trd.sizing import risk_pct_for
from spot_trd.strategy import make_plan
from spot_trd.validate import data_checks

JOURNAL_HINT = "uv run spot"


def trailing_stop(feat: pd.DataFrame, trade: TradeRecord, rules: dict) -> tuple[float, pd.Timestamp | None]:
    """Replays the backtest's stop logic from the entry day. Returns (stop for today, day the stop was breached)."""
    k = rules["exit"]["trail_atr_mult"]
    donchian = rules["exit"].get("trail_mode") == "donchian_mid"
    stop, high = trade.plan["stop"], trade.avg_entry / (1 + rules["market"]["fee_rate"])
    entry_day = trade.first_buy.normalize()
    for day, row in feat[feat.index >= entry_day].iterrows():
        if day > entry_day and row["low"] <= stop:
            return stop, day
        if donchian:
            stop = max(stop, row["dc_mid"])
        elif k:
            high = max(high, row["close"] if day == entry_day else row["high"])
            stop = max(stop, high - k * row["atr"])
    return stop, None


def regime_break_day(feat: pd.DataFrame, trade: TradeRecord) -> pd.Timestamp | None:
    """First daily close since entry where the 1M/1D uptrend was broken (the backtest sells at the next open).

    Replayed from the entry day like the trailing stop, so a break on a day the app was off is not forgotten."""
    since = feat.loc[feat.index >= trade.first_buy.normalize(), "trend_ok"].fillna(False).astype(bool)
    broken = since.index[~since.to_numpy()]
    return broken[0] if len(broken) else None


def upcoming_events(events: dict, card_day: pd.Timestamp) -> list[str]:
    window = card_day + pd.Timedelta(days=events["block_window_days"])
    out = []
    for kind, label in (("fomc_decisions", "FOMC rate decision"), ("cpi_releases", "US CPI release")):
        out += [f"{label} {d}" for d in events.get(kind, []) if card_day <= pd.Timestamp(d) <= window]
    return out


def stop_limit(stop: float, rules: dict) -> str:
    """How to place the protective sell (decision record 2026-10-02: a market stop; the trigger levels are unchanged).

    The fallback keeps the old stop-limit prices for apps that don't offer a market stop on BTC/USDT spot."""
    return (f"STOP MARKET (Binance order type STOP_LOSS) trigger {stop:,.2f}. If your app only offers Stop-Limit, "
            f"use trigger {stop:,.2f}, limit {stop * (1 - rules['exit']['stop_limit_offset']):,.2f}")


def regime_lines(last: pd.Series) -> list[str]:
    yn = lambda b: "yes" if b else "NO"
    return [
        f"BTC close {last['close']:,.2f} | EMA20 {last['ema_pb']:,.0f} | EMA50 {last['ema_fast']:,.0f} | "
        f"EMA200 {last['ema_slow']:,.0f} | RSI {last['rsi']:.0f} | ATR {last['atr']:,.0f} ({last['atr'] / last['close']:.1%})",
        f"Gates: 1M uptrend {yn(last['monthly_up'])} | 1D uptrend {yn(last['daily_up'])} | "
        f"macro calm {yn(not last['risk_off'])} (S&P weak {last['spx_weak']}, DXY surge {last['dxy_surge']}, "
        f"commodity stress {last['commodity_stress']})",
    ]


def history_line(feat: pd.DataFrame, mask: pd.Series, label: str) -> str:
    s = analog_stats(forward_returns(feat["close"]), mask).loc["10d"]
    return (f"History ({label}, {int(s['days'])} days since 2018): BTC 10 days later averaged {s['mean']:+.1%}, "
            f"up {s['pct_up']:.0%} of the time, worst 10% {s['worst_10pct']:+.1%}.")


def hold_section(feat: pd.DataFrame, trade: TradeRecord, rules: dict) -> tuple[list[str], str]:
    last = feat.iloc[-1]
    stop, breached = trailing_stop(feat, trade, rules)
    r_now = (trade.held * last["close"] * (1 - rules["market"]["fee_rate"]) + trade.proceeds - trade.cost) / trade.risk_usdt(rules)
    lines = [f"OPEN POSITION {trade.trade_id}: {trade.held:.5f} BTC, avg entry {trade.avg_entry:,.2f}, "
             f"now {last['close']:,.2f} ({last['close'] / trade.avg_entry - 1:+.1%}, {r_now:+.2f}R)"]
    broke = regime_break_day(feat, trade) if rules["exit"]["regime_exit"] else None
    if broke is not None and breached is not None and broke < breached:
        breached = None  # the trend exit came first; the stop after it no longer applies
    if breached is not None:
        headline = (f"CHECK YOUR STOP. Price hit {stop:,.2f}; if Binance didn't execute your stop order, "
                    "SELL AT MARKET now, then log it.")
        lines += [f"DECISION: STOP WAS HIT on {breached.date()} (low {feat.loc[breached, 'low']:,.2f} <= stop {stop:,.2f}).",
                  "Check Binance: if your stop order executed, log it:",
                  f"  {JOURNAL_HINT} sell --usdt <total received> --btc {trade.held:.5f}",
                  "If it did NOT execute (for example a stop-limit that price gapped through), sell at market now and log it."]
    elif broke is not None:
        when = "at the last daily close" if broke == last.name else f"at the {broke.date()} daily close (while the app was off)"
        headline = f"SELL ALL BTC AT MARKET NOW. The uptrend broke {when}."
        lines += [f"DECISION: SELL ALL AT MARKET NOW. The 1M/1D BTC uptrend broke {when}.",
                  f"  Then log it: {JOURNAL_HINT} sell --usdt <total received> --btc {trade.held:.5f}"]
    else:
        headline = f"HOLD. Move your stop to trigger {stop:,.2f} (market stop)."
        lines += [f"DECISION: HOLD. Set your STOP SELL for {trade.held:.5f} BTC to: {stop_limit(stop, rules)}",
                  "  (Cancel the old stop order first. The stop only ever moves up.)"]
    return lines, headline


def entry_section(feat: pd.DataFrame, book: Book, rules: dict, universe: dict, events: dict,
                  card_day: pd.Timestamp, now: pd.Timestamp) -> tuple[list[str], object, str]:
    last = feat.iloc[-1]
    risk = risk_pct_for(book.cash, rules)
    if book.breaker.halted(now):
        why = book.breaker.events[-1][1]
        return [f"DECISION: NO TRADE. Circuit breaker active until {book.breaker.halt_until.date()} ({why}).",
                "Use the pause to review the journal; don't override it."], None, \
            f"NO ACTION. Trading paused until {book.breaker.halt_until.date()} (circuit breaker). Run `spot review`."
    if not last["regime_ok"]:
        return ["DECISION: NO TRADE. Regime gate blocked (see gates above). Stay in USDT.",
                history_line(feat, ~feat["regime_ok"], "regime blocked")], None, \
            "NO ACTION. Stay in USDT: the BTC trend/macro filter is closed."
    if not last["signal"]:
        trigger = last["ema_pb"] * (1 + rules["setup"]["pullback_tolerance"])
        return ["DECISION: NO TRADE. Uptrend intact but no pullback setup (price not back near EMA20 with RSI < "
                f"{rules['setup']['rsi_max']}). Wait; don't chase.",
                history_line(feat, feat["regime_ok"] & ~feat["pullback"], "uptrend, no pullback")], None, \
            f"NO ACTION. Stay in USDT. A buy plan appears if a daily close is <= {trigger:,.0f} with RSI < {rules['setup']['rsi_max']}."
    blockers = upcoming_events(events, card_day)
    if blockers:
        return [f"DECISION: NO TRADE. Setup present, but high-volatility event in the order window: {', '.join(blockers)}."], \
            None, f"NO ACTION. Setup skipped because of {', '.join(blockers)}."

    plan, why = make_plan(last, book.cash, book.cash, rules, universe)
    if plan is None:
        return [f"DECISION: NO TRADE. Setup present but {why}.",
                "The stop is too wide for the account size, so the position can't clear Binance's minimum order."], None, \
            "NO ACTION. Setup present but too small for Binance's minimum order at this account size."

    valid_until = card_day + pd.Timedelta(days=rules["entry"]["valid_days"])
    lines = [f"DECISION: BUY BTC/USDT, pullback in an uptrend. Risk {risk:.0%} of equity = up to {plan.risk_usdt:.2f} USDT.",
             f"Place these LIMIT BUY orders now. Cancel any still unfilled at {local(valid_until)}:"]
    for n, o in enumerate(plan.orders, 1):
        lines.append(f"  {n}) price {o.price:,.2f}  amount {o.qty:.5f} BTC  (~{o.notional:.2f} USDT)")
    lines += [
        f"Initial stop {plan.stop:,.2f}. As soon as any buy fills, place a STOP SELL for the BTC you hold: "
        f"{stop_limit(plan.stop, rules)}.",
        "No fixed take-profit: the stop trails 2 ATR under the highest price. Run this card daily to move it up.",
        f"Log each fill: {JOURNAL_HINT} buy --usdt <total spent> --btc <BTC received>",
        history_line(feat, feat["setup"], "past pullback setups"),
    ]
    n = len(plan.orders)
    headline = (f"PLACE {n} LIMIT BUY ORDER{'S' if n > 1 else ''} NOW (below). Max loss {plan.risk_usdt:.2f} USDT. "
                f"Cancel unfilled at {local(valid_until)}.")
    return lines, (plan, valid_until), headline


def live_lines(feat: pd.DataFrame, book: Book, rules: dict, ticker: dict, now: pd.Timestamp) -> list[str]:
    """Where the live price sits relative to the levels that matter today. Context only: decisions use daily closes."""
    last = feat.iloc[-1]
    px = ticker["last"]
    when = pd.Timestamp(ticker["timestamp"], unit="ms")
    lines = [f"LIVE {px:,.2f} at {local_hm(when)} (24h {ticker['percentage']:+.2f}%). "
             f"Context only; decisions use the daily close.",
             f"  vs EMA20 {last['ema_pb']:,.0f}: {px / last['ema_pb'] - 1:+.1%} | vs EMA200 {last['ema_slow']:,.0f}: "
             f"{px / last['ema_slow'] - 1:+.1%}"]
    trade = book.open_trade
    active = book.active_plan(now)
    if trade:
        stop, _ = trailing_stop(feat, trade, rules)
        lines.append(f"  Open {trade.trade_id}: {px / stop - 1:+.1%} above your stop {stop:,.2f} | "
                     f"P&L now {px / (trade.avg_entry / (1 + rules['market']['fee_rate'])) - 1:+.1%}")
    if active and active.btc_bought < sum(q for _, q in active.plan["orders"]) - 1e-12:
        nearest = max(p for p, _ in active.plan["orders"])
        lines.append(f"  Resting limit buy {nearest:,.2f}: price must fall {1 - nearest / px:.1%} to fill")
    if trade is None and not active and last["regime_ok"]:
        trigger = last["ema_pb"] * (1 + rules["setup"]["pullback_tolerance"])
        lines.append(f"  Setup watch: a daily close at or below ~{trigger:,.0f} (EMA20 +"
                     f"{rules['setup']['pullback_tolerance']:.0%}) with RSI < {rules['setup']['rsi_max']} "
                     f"creates a buy plan; that's {1 - trigger / px:.1%} below the live price.")
    return lines


def live_section(feat: pd.DataFrame, book: Book, rules: dict, now: pd.Timestamp) -> list[str]:
    from spot_trd.chart import live_snapshot, render  # matplotlib is only needed here

    try:
        ticker, h4 = live_snapshot(rules["market"]["symbol"])
    except Exception as err:  # a live-feed outage must not block the daily decision
        return [f"[WARN] Live price unavailable ({err}). The decision above is unaffected."]
    lines = live_lines(feat, book, rules, ticker, now)
    lines.append(f"  Chart: {render(feat, ticker, h4)}")
    return lines


def build_card(feat: pd.DataFrame, book: Book, rules: dict, universe: dict, events: dict,
               now: pd.Timestamp) -> tuple[str, object]:
    last = feat.iloc[-1]
    card_day = last.name + pd.Timedelta(days=1)
    equity = book.cash
    open_trade = book.open_trade
    if open_trade:
        equity += open_trade.held * last["close"]
    lines = [
        f"=== SPOT-TRD CARD for {card_day.date()} (daily close {last.name.date()}, rules v{rules['version']}) ===",
        f"Account: equity ~{equity:.2f} USDT (cash {book.cash:.2f}). Halal: BTC/USDT spot only, no margin, no Earn.",
        *regime_lines(last),
        "",
    ]
    new_plan, headline = None, ""
    active = book.active_plan(now)
    if open_trade:
        section, headline = hold_section(feat, open_trade, rules)
        lines += section
    if active and (open_trade is None or active.trade_id == open_trade.trade_id):
        filled = active.btc_bought > 0
        valid_until = pd.Timestamp(active.plan["valid_until"])
        lines.append(f"{'Remaining orders' if filled else 'Active plan ' + active.trade_id}: limit buys stay valid "
                     f"until {local(valid_until)}; don't add new ones.")
        if not filled:
            for n, (p, q) in enumerate(active.plan["orders"], 1):
                lines.append(f"  {n}) price {p:,.2f}  amount {q:.5f} BTC")
            lines.append(f"  Stop once filled: {stop_limit(active.plan['stop'], rules)}")
            headline = (f"KEEP YOUR LIMIT BUY(S) until {local(valid_until)} (not placed yet? place them "
                        "now, see below). If one fills: place the stop order, then `spot buy`.")
    elif open_trade is None and (skipped := book.skipped_plan(now)) is not None:
        # The rules never stack plans: a skipped plan's window still blocks a new one, as a resting order would.
        until = pd.Timestamp(skipped.plan["valid_until"])
        headline = f"NO ACTION. You skipped {skipped.trade_id}; no new plan before {local(until)}."
        lines.append(f"DECISION: NO TRADE. You skipped {skipped.trade_id}, whose orders were valid until {local(until)}"
                     ". A new plan can only come after that (the shadow book tracks what the skipped plan does).")
    elif open_trade is None:
        section, new_plan, headline = entry_section(feat, book, rules, universe, events, card_day, now)
        lines += section
    lines.insert(1, f">>> TODAY: {headline}")
    lines += ["", f"Next card: after the next daily close ({daily_close()}). Rules: {rules['strategy']} entries, "
                  "trailing stop, 5%-from-peak and 3-loss circuit breakers."]
    return "\n".join(lines), new_plan


def main() -> None:
    ap = argparse.ArgumentParser(description="Print today's halal BTC spot trade card.")
    ap.add_argument("--no-refresh", action="store_true", help="use cached market data")
    ap.add_argument("--dry-run", action="store_true", help="don't record a new plan in the journal")
    ap.add_argument("--paper", action="store_true", help="use the paper-trading journal")
    ap.add_argument("--no-live", action="store_true", help="skip the live price and chart")
    args = ap.parse_args()
    text, ok = produce_card(args.paper, refresh=not args.no_refresh, record=not args.dry_run, live=not args.no_live)
    print(text)
    if not ok:
        raise SystemExit(1)


def produce_card(paper: bool, refresh: bool = True, record: bool = True, live: bool = True) -> tuple[str, bool]:
    """Full daily card as text. ok=False means the data failed its checks and no decision was made."""
    path = PAPER_JOURNAL_PATH if paper else JOURNAL_PATH
    rules, universe, events = load_rules(), load_universe(), load_events()
    book = load_book(rules, path)
    if book.breaker is None:
        return f">>> TODAY: SETUP NEEDED. Log your capital first: {JOURNAL_HINT} deposit 25", False
    btc, macro = load_data(refresh=refresh)
    feat = build_features(btc, macro, rules)
    now = utcnow()
    issues = [c for c in data_checks(btc, macro, feat, events, now) if c.status in ("WARN", "FAIL")]
    notes = [f"[{c.status}] {c.name}: {c.detail}" for c in issues]
    if any(c.status == "FAIL" for c in issues):
        return "\n".join([">>> TODAY: NO DECISION (data problem). Do nothing; it will retry.", *notes]), False
    missed = []
    if record:
        from spot_trd.catchup import catch_up
        missed = catch_up(feat, rules, universe, events, path, paper)
        book = load_book(rules, path)
    text, new_plan = build_card(feat, book, rules, universe, events, now)
    if missed:
        text += "\n\n" + "\n".join(missed)
    tid = None
    if new_plan and record:
        plan, valid_until = new_plan
        tid = record_plan(plan, rules, path, valid_until=valid_until)
        text += f"\n(Plan recorded as {tid}.)"
    if record:
        current = book.open_trade or book.active_plan(now)
        headline = next(l for l in text.splitlines() if l.startswith(">>> TODAY:")).removeprefix(">>> TODAY: ")
        record_decision(feat, headline, tid or (current.trade_id if current else None), rules, paper)
    if live:
        text += "\n\n" + "\n".join(live_section(feat, load_book(rules, path), rules, now))
    if notes:
        text += "\n\n" + "\n".join(notes)
    try:
        from spot_trd.shadow import card_lines
        shadow = card_lines(load_book(rules, path), feat, rules)
    except Exception as err:  # bookkeeping must never block the daily decision
        shadow = [f"[WARN] Shadow book unavailable ({err})."]
    if shadow:
        text += "\n\n" + "\n".join(shadow)
    if paper:
        text = "[PAPER TRADING]\n" + text
    return text + "\n\n" + status_text(load_book(rules, path)), True


if __name__ == "__main__":
    main()
