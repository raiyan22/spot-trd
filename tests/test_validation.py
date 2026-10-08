import numpy as np
import pandas as pd
import pytest

from spot_trd import journal
from spot_trd.config import load_rules
from spot_trd.review import review_trade
from spot_trd.validate import data_checks, performance_checks
from tests.helpers import LAST_DAY, make_feat

RULES = load_rules()
EVENTS = {"block_window_days": 1, "fomc_decisions": ["2027-01-27"], "cpi_releases": ["2027-01-13"]}
NOW = LAST_DAY + pd.Timedelta(days=1, hours=1)


def market(feat):
    btc = feat[["open", "high", "low", "close"]].copy()
    macro = pd.DataFrame({"spx": 1.0, "gold": 1.0, "oil": 1.0, "dxy": 1.0}, index=feat.index)
    return btc, macro


def by_name(checks):
    return {c.name: c for c in checks}


def test_fresh_data_passes():
    f = make_feat()
    checks = by_name(data_checks(*market(f), f, EVENTS, NOW))
    assert checks["BTC data fresh"].status == "PASS"
    assert checks["Latest features complete"].status == "PASS"
    assert checks["Event calendar coverage"].status == "PASS"


def test_stale_data_fails():
    f = make_feat()
    checks = by_name(data_checks(*market(f), f, EVENTS, NOW + pd.Timedelta(days=3)))
    assert checks["BTC data fresh"].status == "FAIL"


def test_missing_event_dates_warn():
    f = make_feat()
    events = {**EVENTS, "cpi_releases": ["2026-10-14"]}
    assert by_name(data_checks(*market(f), f, events, NOW))["Event calendar coverage"].status == "WARN"


def book_with_trades(tmp_path, results_r):
    """Closed trades that each risked ~0.5 USDT and returned the given R multiples."""
    p = tmp_path / "j.csv"
    journal.main(["deposit", "25"], path=p)
    for i, r in enumerate(results_r):
        tid = f"T{i + 1:03d}"
        details = {"orders": [[100_000, 0.0001]], "stop": 95_100, "valid_until": "2030-01-01", "risk_usdt": 0.5}
        journal.append_event(p, event="plan", trade_id=tid, details=__import__("json").dumps(details),
                             time_utc=f"2026-01-{i + 1:02d}T00:00:00")
        journal.append_event(p, event="buy", trade_id=tid, btc=0.0001, usdt=10.0,
                             time_utc=f"2026-01-{i + 1:02d}T01:00:00")
        book = journal.load_book(RULES, p)
        risk = book.trades[tid].risk_usdt(RULES)
        journal.append_event(p, event="sell", trade_id=tid, btc=0.0001, usdt=10.0 + r * risk,
                             time_utc=f"2026-01-{i + 1:02d}T02:00:00")
    return journal.load_book(RULES, p)


BACKTEST_R = np.array([-1.0] * 30 + [0.5] * 5 + [3.0] * 15)  # avg ~+0.35R, 40% winners


def test_no_trades_is_info(tmp_path):
    p = tmp_path / "j.csv"
    journal.main(["deposit", "25"], path=p)
    [c] = performance_checks(journal.load_book(RULES, p), BACKTEST_R, -0.12, RULES)
    assert c.status == "INFO"


def test_results_in_line_with_backtest_pass(tmp_path):
    book = book_with_trades(tmp_path, [-1, -1, 3, -1, 0.5, 3, -1, -1, 3, -1])
    checks = by_name(performance_checks(book, BACKTEST_R, -0.30, RULES))
    assert checks["Expectancy vs backtest"].status == "PASS"
    assert checks["Loss per trade capped at 1R"].status == "PASS"


def test_much_worse_than_backtest_fails(tmp_path):
    book = book_with_trades(tmp_path, [-1] * 12)  # ~-24% drawdown
    checks = by_name(performance_checks(book, BACKTEST_R, -0.12, RULES))
    assert checks["Expectancy vs backtest"].status == "FAIL"
    assert checks["Drawdown within backtest worst"].status == "FAIL"


def test_loss_beyond_stop_fails(tmp_path):
    book = book_with_trades(tmp_path, [-2.0, 3.0])
    assert by_name(performance_checks(book, BACKTEST_R, -0.30, RULES))["Loss per trade capped at 1R"].status == "FAIL"


def closed_trade(entry_price, exit_price, exit_day, stop=95_000.0, entry_day="2026-09-10"):
    t = journal.TradeRecord("T001", {"orders": [[100_000.0, 0.0001]], "stop": stop}, pd.Timestamp(entry_day))
    fee = RULES["market"]["fee_rate"]
    t.btc_bought = t.btc_sold = 0.0001
    t.cost = 0.0001 * entry_price * (1 + fee)
    t.proceeds = 0.0001 * exit_price * (1 - fee)
    t.first_buy = pd.Timestamp(entry_day) + pd.Timedelta(hours=2)
    t.closed_at = pd.Timestamp(exit_day) + pd.Timedelta(hours=2)
    return t


@pytest.fixture
def flat_market():
    return make_feat(n=40, close=100_000.0, atr=500.0)


def test_review_clean_stop(flat_market):
    # Entry-day close 100,000 - 2*ATR(500) trails the stop to 99,000; the next day's low of 99,000 hits it.
    rv = review_trade(closed_trade(100_000, 98_800, "2026-09-20"), flat_market, RULES)
    assert rv.stop_at_exit == pytest.approx(99_000)
    assert rv.exit_type == "stop" and rv.mistakes == []


def test_review_flags_chase_and_discretionary_exit(flat_market):
    rv = review_trade(closed_trade(101_000, 104_000, "2026-09-20"), flat_market, RULES)
    assert "chased entry" in rv.mistakes
    assert rv.exit_type == "manual" and "discretionary exit" in rv.mistakes


def test_review_flags_late_stop(flat_market):
    rv = review_trade(closed_trade(100_000, 97_000, "2026-09-20"), flat_market, RULES)
    assert "late stop" in rv.mistakes


def test_review_flags_late_regime_exit():
    f = make_feat(n=40, close=100_000.0, atr=500.0)
    f.loc[f.index >= "2026-09-15", "trend_ok"] = False
    rv = review_trade(closed_trade(100_000, 100_500, "2026-09-20"), f, RULES)
    assert rv.exit_type == "regime exit" and "late regime exit" in rv.mistakes
