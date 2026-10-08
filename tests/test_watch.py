import json

import pandas as pd

from spot_trd import journal
from spot_trd.config import load_rules, load_universe, load_watch
from spot_trd.run import build_card
from spot_trd.watch import check_alerts, daily_due
from tests.helpers import make_feat

RULES, U, CFG = load_rules(), load_universe(), load_watch()
NOW = pd.Timestamp("2026-10-01 12:00")
NO_EVENTS = {"block_window_days": 1, "fomc_decisions": [], "cpi_releases": []}


def ticker(px):
    return {"last": px, "timestamp": 1_790_000_000_000, "percentage": 0.0}


def book(tmp_path, plan_orders=None, bought=False, valid_until="2026-10-03T00:00:00", stop=95_000):
    p = tmp_path / "j.csv"
    journal.main(["deposit", "25"], path=p)
    if plan_orders:
        details = {"orders": plan_orders, "stop": stop, "valid_until": valid_until, "risk_usdt": 0.5}
        journal.append_event(p, event="plan", trade_id="T001", details=json.dumps(details), time_utc="2026-09-25T00:00:00")
        if bought:
            journal.append_event(p, event="buy", trade_id="T001", btc=0.0001, usdt=10.0, time_utc="2026-09-25T01:00:00")
    return journal.load_book(RULES, p)


def keys(alerts):
    return [a.key.split(":")[0] for a in alerts]


def test_quiet_when_nothing_is_near(tmp_path):
    assert check_alerts(make_feat(signal=False), book(tmp_path), RULES, ticker(110_000), NOW, CFG) == []


def test_setup_near_alert(tmp_path):
    # Trigger = EMA20 100,000 * 1.01 = 101,000; 101,500 is within 1% of it.
    alerts = check_alerts(make_feat(signal=False), book(tmp_path), RULES, ticker(101_500), NOW, CFG)
    assert keys(alerts) == ["setup-near"]


def test_limit_touch_alert(tmp_path):
    b = book(tmp_path, plan_orders=[[99_000, 0.0001]])
    alerts = check_alerts(make_feat(signal=False), b, RULES, ticker(98_900), NOW, CFG)
    assert "limit-touch" in keys(alerts)
    assert "95,000" in alerts[0].message  # tells you the stop to place


def test_expiry_reminder(tmp_path):
    b = book(tmp_path, plan_orders=[[90_000, 0.0001]], valid_until="2026-10-01T12:30:00")
    assert "expiry" in keys(check_alerts(make_feat(signal=False), b, RULES, ticker(100_000), NOW, CFG))


def test_stop_near_and_breach(tmp_path):
    f = make_feat(n=30, close=100_000.0, atr=2_000.0, signal=False)
    b = book(tmp_path, plan_orders=[[100_000, 0.0001]], bought=True, valid_until="2026-09-27T00:00:00")
    stop = 97_000  # later highs 101,000 - 2*ATR(2,000)
    assert keys(check_alerts(f, b, RULES, ticker(stop * 1.005), NOW, CFG)) == ["stop-near"]
    assert keys(check_alerts(f, b, RULES, ticker(stop * 0.99), NOW, CFG)) == ["stop-breach"]


def test_daily_due_after_run_time_once_per_day():
    assert not daily_due(pd.Timestamp("2026-10-02 00:03"), "2026-10-01", "00:05")
    assert daily_due(pd.Timestamp("2026-10-02 00:06"), "2026-10-01", "00:05")
    assert not daily_due(pd.Timestamp("2026-10-02 09:00"), "2026-10-02", "00:05")
    assert daily_due(pd.Timestamp("2026-10-02 14:00"), "2026-10-01", "00:05")  # PC was off at 00:05: catch up


def test_card_starts_with_clear_headline(tmp_path):
    b = book(tmp_path)
    text, _ = build_card(make_feat(signal=False), b, RULES, U, NO_EVENTS, NOW)
    headline = text.splitlines()[1]
    assert headline.startswith(">>> TODAY: NO ACTION") and "101,000" in headline
    text, _ = build_card(make_feat(), b, RULES, U, NO_EVENTS, NOW)
    assert text.splitlines()[1].startswith(">>> TODAY: PLACE")
