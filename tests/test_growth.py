import json

import numpy as np
import pandas as pd

from spot_trd import growth
from spot_trd.config import load_rules
from spot_trd.journal import append_event

RULES = load_rules()


def journal(tmp_path, rows):
    p = tmp_path / "j.csv"
    for r in rows:
        append_event(p, **r)
    return p


def btc(prices, start="2026-10-01"):
    idx = pd.date_range(start, periods=len(prices), freq="D")
    return pd.DataFrame({"close": prices}, index=idx)


PLAN = json.dumps({"orders": [[100.0, 0.5]], "stop": 90.0, "risk_usdt": 5.0, "valid_until": "2026-10-04T00:00:00",
                   "signal_date": "2026-10-01", "rules_version": 2, "strategy": "pullback"})


def test_realized_and_unrealized_are_kept_apart(tmp_path, monkeypatch):
    monkeypatch.setattr(growth, "EXPERIMENT_FILE", tmp_path / "e.json")
    monkeypatch.setattr(growth, "EQUITY_CSV", tmp_path / "eq.csv")
    p = journal(tmp_path, [
        dict(event="deposit", usdt=300.0, time_utc="2026-10-01T00:00:00"),
        dict(event="plan", trade_id="T001", details=PLAN, time_utc="2026-10-01T00:05:00"),
        dict(event="buy", trade_id="T001", btc=0.5, usdt=50.0, time_utc="2026-10-02T03:00:00"),
    ])
    s = growth.compute(p, btc([100, 120, 150]), tmp_path / "none.csv", pd.Timestamp("2026-10-03T12:00:00"), RULES)
    assert s.realized_pnl == 0 and s.realized_equity == 300.0           # nothing closed: no gain is counted
    assert abs(s.marked_equity - (250 + 0.5 * 150)) < 1e-9 and abs(s.unrealized_pnl - 25.0) < 1e-9
    assert not any(m["secured_now"] for m in s.milestones.values())


def test_milestones_use_realized_equity_only(tmp_path, monkeypatch):
    monkeypatch.setattr(growth, "EXPERIMENT_FILE", tmp_path / "e.json")
    monkeypatch.setattr(growth, "EQUITY_CSV", tmp_path / "eq.csv")
    p = journal(tmp_path, [
        dict(event="deposit", usdt=300.0, time_utc="2026-10-01T00:00:00"),
        dict(event="plan", trade_id="T001", details=PLAN, time_utc="2026-10-01T00:05:00"),
        dict(event="buy", trade_id="T001", btc=0.5, usdt=50.0, fee_usdt=0.05, time_utc="2026-10-01T10:00:00"),
        dict(event="sell", trade_id="T001", btc=0.5, usdt=75.0, fee_usdt=0.075, time_utc="2026-10-02T10:00:00"),
    ])
    s = growth.compute(p, btc([100, 120, 150]), tmp_path / "none.csv", pd.Timestamp("2026-10-03T12:00:00"), RULES)
    assert abs(s.realized_pnl - (75 - 0.075 - 50 - 0.05)) < 1e-9
    assert s.realized_equity > 324.8
    assert s.milestones[310]["secured_now"] and s.milestones[320]["secured_now"] and not s.milestones[330]["secured_now"]
    assert s.milestones[320]["reached"] == pd.Timestamp("2026-10-02") and s.milestones[330]["reached"] is None
    assert len(s.closed) == 1 and s.win_rate == 1.0 and s.longest_losing_streak == 0
    assert abs(s.fees_logged - 0.125) < 1e-9 and s.days_since_last_trade == 1


def test_extra_deposits_are_flagged_and_do_not_count_as_growth(tmp_path, monkeypatch):
    monkeypatch.setattr(growth, "EXPERIMENT_FILE", tmp_path / "e.json")
    monkeypatch.setattr(growth, "EQUITY_CSV", tmp_path / "eq.csv")
    p = journal(tmp_path, [
        dict(event="deposit", usdt=300.0, time_utc="2026-10-01T00:00:00"),
        dict(event="deposit", usdt=100.0, time_utc="2026-10-02T00:00:00"),
    ])
    s = growth.compute(p, btc([100, 100, 100]), tmp_path / "none.csv", pd.Timestamp("2026-10-03T12:00:00"), RULES)
    assert s.contributions == 100.0
    assert s.marked_equity == 300.0 and s.realized_equity == 300.0     # the extra 100 is not counted as profit


def test_drawdown_and_losing_streak(tmp_path, monkeypatch):
    monkeypatch.setattr(growth, "EXPERIMENT_FILE", tmp_path / "e.json")
    monkeypatch.setattr(growth, "EQUITY_CSV", tmp_path / "eq.csv")
    rows = [dict(event="deposit", usdt=300.0, time_utc="2026-10-01T00:00:00")]
    for i, (tid, out) in enumerate((("T001", 48.0), ("T002", 47.0))):
        rows += [dict(event="plan", trade_id=tid, details=PLAN, time_utc=f"2026-10-0{i + 1}T00:05:00"),
                 dict(event="buy", trade_id=tid, btc=0.5, usdt=50.0, time_utc=f"2026-10-0{i + 1}T01:00:00"),
                 dict(event="sell", trade_id=tid, btc=0.5, usdt=out, time_utc=f"2026-10-0{i + 1}T12:00:00")]
    p = journal(tmp_path, rows)
    s = growth.compute(p, btc([100, 100, 100, 100]), tmp_path / "none.csv", pd.Timestamp("2026-10-04T12:00:00"), RULES)
    assert s.longest_losing_streak == 2 and s.current_losing_streak == 2 and s.win_rate == 0.0
    assert abs(s.realized_equity - 295.0) < 1e-9 and abs(s.max_dd - (295 / 300 - 1)) < 1e-9


def test_waiting_days_come_from_the_decision_log(tmp_path, monkeypatch):
    monkeypatch.setattr(growth, "EXPERIMENT_FILE", tmp_path / "e.json")
    monkeypatch.setattr(growth, "EQUITY_CSV", tmp_path / "eq.csv")
    p = journal(tmp_path, [dict(event="deposit", usdt=300.0, time_utc="2026-10-01T00:00:00")])
    dec = tmp_path / "d.csv"
    pd.DataFrame({"card_day": ["2026-09-30", "2026-10-01", "2026-10-02", "2026-10-03"],
                  "reason": ["no_pullback", "no_pullback", "gate:monthly", "buy_plan"]}).to_csv(dec, index=False)
    s = growth.compute(p, btc([100, 100, 100, 100]), dec, pd.Timestamp("2026-10-04T12:00:00"), RULES)
    assert s.cards == 3 and s.waiting_days == 2                      # the 09-30 card predates the experiment


def test_init_refuses_to_wipe_a_journal_with_trades(tmp_path, monkeypatch):
    p = journal(tmp_path, [dict(event="deposit", usdt=25.0), dict(event="plan", trade_id="T001", details=PLAN)])
    monkeypatch.setattr(growth, "PAPER_JOURNAL_PATH", p)
    monkeypatch.setattr(growth, "EXPERIMENT_FILE", tmp_path / "e.json")
    try:
        growth.init_experiment()
        raised = False
    except SystemExit:
        raised = True
    assert raised and p.exists()
