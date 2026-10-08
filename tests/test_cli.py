import pandas as pd
import pytest

from spot_trd import cli, journal
from spot_trd.config import load_rules
from spot_trd.data import retry
from spot_trd.run import live_lines
from tests.helpers import make_feat

RULES = load_rules()
TICKER = {"last": 105_000.0, "timestamp": 1_790_000_000_000, "percentage": 1.2}
NOW = pd.Timestamp("2026-10-01 12:00")


def empty_book(tmp_path):
    p = tmp_path / "j.csv"
    journal.main(["deposit", "25"], path=p)
    return journal.load_book(RULES, p)


def test_setup_watch_shows_trigger_price(tmp_path):
    lines = live_lines(make_feat(signal=False), empty_book(tmp_path), RULES, TICKER, NOW)
    watch = next(l for l in lines if "Setup watch" in l)
    assert "101,000" in watch  # EMA20 100,000 + 1% tolerance
    assert "3.8% below the live price" in watch


def test_no_setup_watch_when_regime_blocked(tmp_path):
    lines = live_lines(make_feat(signal=False, trend_ok=False), empty_book(tmp_path), RULES, TICKER, NOW)
    assert not any("Setup watch" in l for l in lines)


def test_open_trade_shows_distance_to_stop(tmp_path):
    p = tmp_path / "j.csv"
    journal.main(["deposit", "25"], path=p)
    details = '{"orders": [[100000, 0.0001]], "stop": 95000, "valid_until": "2026-10-03T00:00:00", "risk_usdt": 0.5}'
    journal.append_event(p, event="plan", trade_id="T001", details=details, time_utc="2026-09-20T00:00:00")
    journal.append_event(p, event="buy", trade_id="T001", btc=0.0001, usdt=10.0, time_utc="2026-09-20T01:00:00")
    lines = live_lines(make_feat(signal=False), journal.load_book(RULES, p), RULES, TICKER, NOW)
    assert any("above your stop" in l for l in lines)


def test_mode_defaults_to_paper_and_switches(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "MODE_FILE", tmp_path / "mode")
    assert cli.get_mode() == "paper"
    cli.set_mode("live")
    assert cli.get_mode() == "live"


def test_unknown_command_exits(monkeypatch):
    monkeypatch.setattr("sys.argv", ["spot", "frobnicate"])
    with pytest.raises(SystemExit):
        cli.main()


def test_retry_recovers_then_gives_up():
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise ConnectionError("blip")
        return "ok"

    assert retry(flaky, tries=3, wait=0) == "ok"
    with pytest.raises(ConnectionError):
        retry(lambda: (_ for _ in ()).throw(ConnectionError("down")), tries=2, wait=0)
