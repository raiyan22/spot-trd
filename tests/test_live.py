import json

import pandas as pd
import pytest

from spot_trd import journal
from spot_trd.config import load_rules, load_universe
from spot_trd.run import build_card, trailing_stop
from tests.helpers import make_feat as feat

RULES, U = load_rules(), load_universe()
NO_EVENTS = {"block_window_days": 1, "fomc_decisions": [], "cpi_releases": []}


def journal_main(path, *argv):
    journal.main(list(argv), path=path)


@pytest.fixture
def jpath(tmp_path):
    p = tmp_path / "journal.csv"
    journal_main(p, "deposit", "25")
    return p


def card(f, path, now=pd.Timestamp("2026-10-01 01:00"), events=NO_EVENTS):
    return build_card(f, journal.load_book(RULES, path), RULES, U, events, now)


def test_buy_card_sizes_within_risk(jpath):
    text, new_plan = card(feat(), jpath)
    assert "DECISION: BUY" in text
    plan, valid_until = new_plan
    assert plan.risk_usdt <= 25 * 0.02
    assert valid_until == pd.Timestamp("2026-10-03")


def test_event_blocks_new_entries(jpath):
    events = {**NO_EVENTS, "fomc_decisions": ["2026-10-02"]}
    text, new_plan = card(feat(), jpath, events=events)
    assert new_plan is None and "FOMC" in text


def test_no_pullback_means_no_trade(jpath):
    text, new_plan = card(feat(signal=False), jpath)
    assert new_plan is None and "no pullback" in text


def test_full_trade_cycle_and_hold_card(jpath):
    f = feat()
    _, (plan, valid_until) = card(f, jpath)
    journal.record_plan(plan, RULES, jpath, valid_until=valid_until)
    o = plan.orders[0]
    journal_main(jpath, "buy", "--usdt", f"{o.notional:.4f}", "--btc", f"{o.qty}", "--time", "2026-09-20T00:00:00")

    book = journal.load_book(RULES, jpath)
    assert book.open_trade is not None
    assert book.cash == pytest.approx(25 - o.notional)

    text, new_plan = card(f, jpath)
    assert "DECISION: HOLD" in text and new_plan is None
    stop, breached = trailing_stop(f, book.open_trade, RULES)
    assert stop >= plan.stop and breached is None

    text, _ = card(feat(trend_ok=False), jpath)
    assert "SELL ALL AT MARKET" in text

    journal_main(jpath, "sell", "--usdt", f"{o.notional * 0.98:.4f}", "--btc", f"{o.qty}")
    book = journal.load_book(RULES, jpath)
    assert book.open_trade is None
    [closed] = book.closed_trades
    assert closed.pnl < 0
    assert book.breaker.losses == 1


def test_unplanned_buy_rejected(jpath):
    with pytest.raises(SystemExit, match="Only buy what a trade card"):
        journal_main(jpath, "buy", "--usdt", "10", "--btc", "0.0001")


def test_oversell_rejected_as_short(jpath):
    _, (plan, valid_until) = card(feat(), jpath)
    journal.record_plan(plan, RULES, jpath, valid_until=valid_until)
    journal_main(jpath, "buy", "--usdt", "6", "--btc", "0.00006", "--time", "2026-10-01T02:00:00")
    with pytest.raises(SystemExit, match="short selling"):
        journal_main(jpath, "sell", "--usdt", "12", "--btc", "0.00012")


def test_buy_beyond_cash_rejected(jpath):
    _, (plan, valid_until) = card(feat(), jpath)
    journal.record_plan(plan, RULES, jpath, valid_until=valid_until)
    with pytest.raises(SystemExit, match="exceeds cash"):
        journal_main(jpath, "buy", "--usdt", "30", "--btc", "0.0003", "--time", "2026-10-01T02:00:00")


def test_three_losses_halt_new_entries(jpath):
    f = feat()
    for _ in range(3):
        _, (plan, _) = card(f, jpath, now=pd.Timestamp("2026-10-01 01:00"))
        journal.record_plan(plan, RULES, jpath, valid_until=pd.Timestamp("2026-10-03"))
        o = plan.orders[0]
        journal_main(jpath, "buy", "--usdt", f"{o.notional:.4f}", "--btc", f"{o.qty}", "--time", "2026-10-01T02:00:00")
        journal_main(jpath, "sell", "--usdt", f"{o.notional * 0.97:.4f}", "--btc", f"{o.qty}", "--time", "2026-10-01T03:00:00")
    text, new_plan = card(f, jpath, now=pd.Timestamp("2026-10-01 04:00"))
    assert new_plan is None and "Circuit breaker active" in text


def test_plan_details_round_trip(jpath):
    _, (plan, valid_until) = card(feat(), jpath)
    tid = journal.record_plan(plan, RULES, jpath, valid_until=valid_until)
    [row] = [e for e in journal.read_events(jpath) if e["event"] == "plan"]
    details = json.loads(row["details"])
    assert row["trade_id"] == tid == "T001"
    assert details["stop"] == pytest.approx(plan.stop)
    assert details["rules_version"] == RULES["version"]
