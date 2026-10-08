import pandas as pd

from spot_trd import decisions
from spot_trd.config import load_rules
from spot_trd.decisions import analyze, outcome_label, reason_code, record_decision
from tests.helpers import make_feat

RULES = load_rules()


def test_reason_codes():
    ok = make_feat(signal=False).iloc[-1]
    blocked = make_feat(signal=False, trend_ok=False).iloc[-1]
    assert reason_code("PLACE 2 LIMIT BUY ORDERS NOW", ok) == "buy_plan"
    assert reason_code("HOLD. Move your stop", ok) == "hold"
    assert reason_code("NO ACTION. Stay in USDT. A buy plan appears if", ok) == "no_pullback"
    assert reason_code("NO ACTION. Stay in USDT: the BTC trend/macro filter is closed.", blocked) == "gate:monthly+daily"
    assert reason_code("NO ACTION. Trading paused until 2026-11-01", ok) == "circuit_breaker"
    assert reason_code("NO ACTION. Setup skipped because of CPI 2026-10-14.", ok) == "event_window"


def test_outcome_labels():
    assert outcome_label("neutral", 0.08) == "missed rally"
    assert outcome_label("neutral", -0.07) == "avoided drop"
    assert outcome_label("neutral", 0.01) == "quiet (no big move)"
    assert outcome_label("neutral", None).startswith("pending")


def test_one_row_per_day(tmp_path, monkeypatch):
    monkeypatch.setattr(decisions, "LOG_PAPER", tmp_path / "d.csv")
    f = make_feat(signal=False)
    record_decision(f, "NO ACTION. Stay in USDT.", None, RULES, paper=True)
    record_decision(f, "NO ACTION. Stay in USDT.", None, RULES, paper=True)
    log = pd.read_csv(tmp_path / "d.csv")
    assert len(log) == 1
    assert log.loc[0, "reason"] == "no_pullback" and log.loc[0, "card_day"] == "2026-10-01"


def test_analysis_attributes_missed_rallies_and_avoided_drops():
    idx = pd.date_range("2026-01-01", periods=40, freq="D")
    close = pd.Series([100.0] * 10 + [110.0] * 15 + [95.0] * 15, index=idx)
    log = pd.DataFrame({
        "card_day": ["2026-01-02", "2026-01-17"], "close_date": ["2026-01-01", "2026-01-16"],
        "kind": ["neutral", "neutral"], "reason": ["gate:macro", "no_pullback"], "trade_id": ["", ""],
        "close": [100.0, 110.0], "rsi": [50.0, 60.0],
    })
    text = analyze(log, close, None)
    assert "| gate:macro | 1 | 1 | 0 |" in text      # stayed out, BTC +10%: missed rally
    assert "| no_pullback | 1 | 0 | 1 |" in text     # stayed out, BTC -13.6%: avoided drop
