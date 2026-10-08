"""Catch-up: replay the daily cards for closes that passed while the app was off.

Each missed close gets the card it would have had, from data up to that close only (same rules, same code). A buy plan
from a missed day is recorded if its limit orders are still valid now; an expired one is reported, never chased.
Open-position exits need no replay here: the trailing stop and the trend-exit check already replay from the entry day.
"""
import csv

import pandas as pd

from spot_trd.decisions import log_path, record_decision
from spot_trd.journal import load_book, record_plan, utcnow

MAX_DAYS = 60  # older gaps are only summarised; a plan from then has long expired
HEADER = "WHILE THE APP WAS OFF"


def last_card_day(paper: bool) -> pd.Timestamp | None:
    path = log_path(paper)
    if not path.exists():
        return None
    with open(path, newline="", encoding="utf-8") as f:
        days = [r["card_day"] for r in csv.DictReader(f)]
    return pd.Timestamp(max(days)) if days else None


def missed_closes(feat: pd.DataFrame, last_day: pd.Timestamp | None) -> pd.DatetimeIndex:
    """Completed daily closes after the last card and before the latest close (which gets today's normal card)."""
    if last_day is None:  # first run ever: nothing was missed
        return feat.index[:0]
    return feat.index[(feat.index >= last_day) & (feat.index < feat.index[-1])]


def catch_up(feat: pd.DataFrame, rules: dict, universe: dict, events: dict, path, paper: bool,
             run_at: str = "00:05") -> list[str]:
    """Replay missed cards, record them in the decision log, and return a short report (empty if nothing was missed)."""
    from spot_trd.run import build_card

    missed = missed_closes(feat, last_card_day(paper))
    if not len(missed):
        return []
    hh, mm = map(int, run_at.split(":"))
    now = utcnow()
    lines = [f"{HEADER} ({len(missed)} daily close{'s' if len(missed) > 1 else ''} replayed with the same rules):"]
    if len(missed) > MAX_DAYS:
        lines.append(f"  {len(missed) - MAX_DAYS} older closes skipped (any plan from them has expired).")
        missed = missed[-MAX_DAYS:]
    for close in missed:
        sub = feat.loc[:close]
        card_day = close + pd.Timedelta(days=1)
        at = card_day + pd.Timedelta(hours=hh, minutes=mm)
        book = load_book(rules, path)
        text, new_plan = build_card(sub, book, rules, universe, events, at)
        headline = next(l for l in text.splitlines() if l.startswith(">>> TODAY:")).removeprefix(">>> TODAY: ")
        note, tid = "", None
        if new_plan:
            plan, valid_until = new_plan
            if valid_until > now:
                tid = record_plan(plan, rules, path, valid_until=valid_until)
                touched = [o.price for o in plan.orders if (feat.loc[card_day:, "low"] <= o.price).any()]
                note = (f" -> plan {tid} recorded; its limit buys are still valid until {valid_until:%Y-%m-%d %H:%M} UTC."
                        + (f" Price already traded at {', '.join(f'{p:,.0f}' for p in touched)} since then."
                           if touched else ""))
            else:
                note = f" -> expired {valid_until:%Y-%m-%d %H:%M} UTC. Nothing to do; don't chase it."
        current = book.open_trade or book.active_plan(at)
        record_decision(sub, headline, tid or (current.trade_id if current else None), rules, paper)
        lines.append(f"  {card_day.date()}: {headline}{note}")
    return lines
