import json

import pandas as pd
import pytest

from spot_trd import cloud, journal, reply, shadow
from spot_trd.config import load_rules
from tests.helpers import make_feat

RULES = load_rules()
AT = pd.Timestamp("2026-09-25 10:00")


def add_plan(path, tid, signal, orders, stop, valid_until):
    journal.append_event(path, event="plan", trade_id=tid, time_utc=f"{signal}T00:05:00",
                         details=json.dumps({"orders": orders, "stop": stop, "risk_usdt": 0.5,
                                             "valid_until": valid_until, "signal_date": signal}))


@pytest.fixture
def jpath(tmp_path):
    p = tmp_path / "j.csv"
    journal.main(["deposit", "25"], path=p)
    return p


# -- reply parsing -------------------------------------------------------------------------------------------------
def test_parse_bought_in_either_order_and_with_a_fill_time():
    assert reply.parse("bought 6.49 0.0000799", AT) == (
        "buy", ["buy", "--usdt", "6.49000000", "--btc", "0.00007990", "--time", AT.isoformat(),
                "--note", "logged from a GitHub reply"])
    cmd, args = reply.parse("Sold: 0.0000799 btc, 6.62 usdt", AT)
    assert cmd == "sell" and args[2] == "6.62000000" and args[4] == "0.00007990"
    _, args = reply.parse("bought 6.49 0.0000799 2026-09-24 14:05", AT)  # typed in UTC+6
    assert args[6] == "2026-09-24T08:05:00"


def test_parse_ignores_quoted_email_text():
    body = "\n\nskip\n\nOn Fri, Oct 16, 2026 at 04:30 github-actions wrote:\n> PLACE 2 LIMIT BUY ORDERS"
    assert reply.parse(body, AT) == ("skip", ["skip", "--note", "via GitHub reply"])
    assert reply.parse("> quoted\nnote moved stop late", AT) == ("note", ["note", "moved stop late"])


@pytest.mark.parametrize("body", ["", "hello there", "bought 6.49", "bought 6.49 7.1", "note",
                                  "bought 6.49 0.0000799 2026-09-30 22:00"])
def test_parse_rejects_what_it_cannot_log_safely(body):
    with pytest.raises(ValueError):
        reply.parse(body, AT)


def test_notifications_explain_how_to_reply():
    hint = cloud.reply_hint("PLACE 2 LIMIT BUY ORDERS NOW (below).")
    assert "`skip`" in hint and "`bought" in hint and "reply to this email" in hint
    assert "`sold" in cloud.reply_hint("HOLD. Move your stop to trigger 80,000.00 (market stop).")


# -- journal: skip and duplicate plans -----------------------------------------------------------------------------
def test_skip_marks_the_plan_and_ends_it(jpath):
    add_plan(jpath, "T001", "2026-09-24", [[99_500.0, 0.0001]], 95_000.0, "2026-09-27T00:00:00")
    journal.main(["skip"], path=jpath)
    t = journal.load_book(RULES, jpath).trades["T001"]
    assert t.skipped and t.cancelled
    assert journal.load_book(RULES, jpath).active_plan(pd.Timestamp("2026-09-26")) is None


def test_a_plan_recorded_twice_for_one_close_counts_once(jpath):
    add_plan(jpath, "T001", "2026-09-24", [[99_500.0, 0.0001]], 95_000.0, "2026-09-27T00:00:00")
    add_plan(jpath, "T002", "2026-09-24", [[99_500.0, 0.0001]], 95_000.0, "2026-09-27T00:00:00")
    journal.append_event(jpath, event="buy", trade_id="T002", btc=0.0001, usdt=9.95, time_utc="2026-09-25T10:00:00")
    book = journal.load_book(RULES, jpath)
    assert list(book.trades) == ["T001"] and book.trades["T001"].btc_bought == pytest.approx(0.0001)


# -- shadow book ---------------------------------------------------------------------------------------------------
def test_shadow_fills_the_card_orders_and_trails_the_stop(jpath):
    add_plan(jpath, "T001", "2026-09-24", [[99_500.0, 0.0001], [90_000.0, 0.0001]], 95_000.0, "2026-09-27T00:00:00")
    feat = make_feat()  # flat 100k, lows 99k: the first limit trades through, the second never does
    s = shadow.simulate(journal.load_book(RULES, jpath).trades["T001"], feat, RULES)
    assert s.status == "open" and s.qty == pytest.approx(0.0001) and s.entry_date == pd.Timestamp("2026-09-25")
    assert s.stop_now == pytest.approx(101_000 - 2 * 2_000)  # 2-ATR chandelier under the high
    assert s.pnl == pytest.approx(0.0001 * 100_000 * 0.999 - 0.0001 * 99_500 * 1.001)


def test_shadow_unfilled_and_waiting(jpath):
    add_plan(jpath, "T001", "2026-09-24", [[90_000.0, 0.0001]], 85_000.0, "2026-09-27T00:00:00")
    add_plan(jpath, "T002", "2026-09-29", [[90_000.0, 0.0001]], 85_000.0, "2026-10-02T00:00:00")
    book = journal.load_book(RULES, jpath)
    assert shadow.simulate(book.trades["T001"], make_feat(), RULES).status == "unfilled"
    assert shadow.simulate(book.trades["T002"], make_feat(), RULES).status == "waiting"


def test_card_line_compares_following_with_what_you_did(jpath, monkeypatch):
    monkeypatch.setattr(shadow, "utcnow", lambda: pd.Timestamp("2026-09-30 12:00"))
    add_plan(jpath, "T001", "2026-09-24", [[99_500.0, 0.0001]], 95_000.0, "2026-09-27T00:00:00")
    journal.main(["skip", "--trade", "T001"], path=jpath)
    lines = shadow.card_lines(journal.load_book(RULES, jpath), make_feat(), RULES)
    assert lines[0].startswith("SHADOW BOOK") and "what you did +0.00 USDT" in lines[0]
    assert "You: skipped (you said so)" in lines[1] and "still open" in lines[1]


def test_overlapping_plan_is_left_out_of_the_follower_total(jpath):
    add_plan(jpath, "T001", "2026-09-20", [[99_500.0, 0.0001]], 95_000.0, "2026-09-23T00:00:00")
    add_plan(jpath, "T002", "2026-09-25", [[99_500.0, 0.0001]], 95_000.0, "2026-09-28T00:00:00")
    rows = shadow.build(journal.load_book(RULES, jpath), make_feat(), RULES)
    assert [r.overlap for r in rows] == [False, True]  # a follower was still holding T001


def test_a_skipped_plan_blocks_a_new_plan_until_it_expires(jpath):
    from spot_trd.config import load_universe
    from spot_trd.run import build_card

    events = {"block_window_days": 1, "fomc_decisions": [], "cpi_releases": []}
    add_plan(jpath, "T001", "2026-09-29", [[99_500.0, 0.0001]], 95_000.0, "2026-10-02T00:00:00")
    journal.main(["skip"], path=jpath)
    book = journal.load_book(RULES, jpath)
    text, new_plan = build_card(make_feat(), book, RULES, load_universe(), events, pd.Timestamp("2026-10-01 00:05"))
    assert new_plan is None and ">>> TODAY: NO ACTION. You skipped T001" in text
    _, new_plan = build_card(make_feat(), book, RULES, load_universe(), events, pd.Timestamp("2026-10-02 00:05"))
    assert new_plan is not None  # the window is over: the rules may plan again


def test_times_are_shown_in_utc_plus_6():
    from spot_trd import clock
    assert clock.local("2026-10-18 00:00") == "2026-10-18 06:00 UTC+6"
    assert clock.daily_close() == "06:00 UTC+6"
    assert clock.from_local("2026-10-18 06:00") == pd.Timestamp("2026-10-18 00:00")
