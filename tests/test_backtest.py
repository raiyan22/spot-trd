import copy

import pandas as pd

from spot_trd.backtest import run_backtest
from spot_trd.config import load_rules, load_universe

U = load_universe()
RULES = load_rules()
# Pin fixed-target exits so these scenarios don't depend on the live config.
RULES["exit"].update(tp1_r=1.5, tp2_r=3.0, trail_atr_mult=None, regime_exit=False, max_hold_days=10)

# Day 0 is a signal: close 100, ATR 2 -> limit buys 99.5 / 98.5, stop 96.5, R ~2.5, TP1 ~102.75, TP2 ~106.5.
SETUP_BAR = (100, 101, 99.8, 100)


def frame(bars, trend_ok=None):
    idx = pd.date_range("2024-01-01", periods=len(bars), freq="D")
    df = pd.DataFrame(bars, index=idx, columns=["open", "high", "low", "close"], dtype=float)
    df["atr"] = 2.0
    df["signal"] = False
    df.iloc[0, df.columns.get_loc("signal")] = True
    df["trend_ok"] = True if trend_ok is None else trend_ok
    return df


def run(bars, rules=RULES, trend_ok=None):
    return run_backtest(frame(bars, trend_ok), rules, U, initial_capital=100_000, risk_pct=0.01)


def with_exit(**changes):
    r = copy.deepcopy(RULES)
    r["exit"].update(changes)
    return r


def test_stop_and_target_in_same_bar_counts_as_stop():
    res = run([SETUP_BAR, (100, 100, 98, 99), (99, 110, 96, 100)])
    [t] = res.trades
    assert t.exit_reason == "stop"
    assert -1.01 < t.r_multiple < -0.95
    assert t.pnl >= -1_000 - 1e-6  # never more than 1% of equity


def test_tp1_moves_stop_to_breakeven():
    res = run([SETUP_BAR, (100, 100, 98, 99), (99, 103, 99, 102.5), (102, 102, 98, 99)])
    [t] = res.trades
    assert t.exit_reason == "breakeven"
    assert t.pnl > 0


def test_tp2_full_winner():
    res = run([SETUP_BAR, (100, 100, 98, 99), (99, 107, 99, 106.8)])
    [t] = res.trades
    assert t.exit_reason == "tp2"
    assert t.r_multiple > 1.8  # half at 1.5R + half at 3R = 2.25R gross, less fees and slippage


def test_unfilled_orders_expire():
    res = run([SETUP_BAR, (100, 102, 99.9, 101), (101, 103, 100, 102), (102, 102, 90, 91)])
    assert res.trades == []
    assert res.unfilled == 1
    assert res.equity.iloc[-1] == 100_000


def test_max_hold_exits_at_close():
    flat = (99.5, 100, 99, 99.6)
    res = run([SETUP_BAR, (100, 100, 98, 99)] + [flat] * 12)
    [t] = res.trades
    assert t.exit_reason == "time"


def test_trailing_stop_ratchets_up_and_exits():
    rules = with_exit(tp1_r=None, tp2_r=None, max_hold_days=None, trail_atr_mult=2.0)
    bars = [SETUP_BAR, (100, 100, 98, 99), (99, 106, 99, 105), (105, 112, 105, 111), (111, 111, 107, 108)]
    res = run(bars, rules)
    [t] = res.trades
    # Highest high 112 - 2*ATR(2) = 108 trailing stop, hit on the last bar.
    assert t.exit_reason == "trail"
    assert t.r_multiple > 2


def test_regime_exit_sells_at_close():
    rules = with_exit(tp1_r=None, tp2_r=None, max_hold_days=None, regime_exit=True)
    bars = [SETUP_BAR, (100, 100, 98, 99), (99, 101, 98, 100), (100, 101, 97, 97.5)]
    res = run(bars, rules, trend_ok=[True, True, True, False])
    [t] = res.trades
    assert t.exit_reason == "regime"
    assert t.exit_date == pd.Timestamp("2024-01-04")


def test_trend_strategy_buys_at_next_open():
    rules = copy.deepcopy(RULES)
    rules["strategy"] = "trend"
    rules["exit"].update(stop_atr_mult=3.0, tp1_r=None, tp2_r=None, max_hold_days=None, regime_exit=True)
    bars = [SETUP_BAR, (101, 103, 100, 102), (102, 103, 101, 102)]
    res = run(bars, rules, trend_ok=[True, True, False])
    [t] = res.trades
    assert t.entry_date == pd.Timestamp("2024-01-02")
    assert abs(t.avg_entry - 101 * 1.001 * 1.001) < 1e-6  # next open + 0.1% slippage, buy fee included


def test_regime_exit_fills_next_open_with_slippage():
    # The break is only known at the close of day 3, so the sell happens at day 4's open (96), not at day 3's close.
    rules = with_exit(tp1_r=None, tp2_r=None, max_hold_days=None, regime_exit=True)
    bars = [SETUP_BAR, (100, 100, 98, 99), (99, 101, 98, 100), (100, 101, 97, 97.5), (97.8, 99, 97, 98)]
    res = run(bars, rules, trend_ok=[True, True, True, False, False])
    [t] = res.trades
    assert t.exit_reason == "regime" and t.exit_date == pd.Timestamp("2024-01-05")
    assert abs(t.proceeds / t.qty - 97.8 * 0.999 * 0.999) < 1e-6  # open less slippage, sell fee deducted


def test_limit_touch_is_not_a_fill_but_a_trade_through_is():
    touch = run([SETUP_BAR, (100, 101, 99.5, 100), (100, 101, 99.6, 100), (100, 100, 99.6, 100)])   # low == 1st limit
    assert touch.trades == [] and touch.unfilled == 1
    through = run([SETUP_BAR, (100, 101, 99.4, 100), (100, 101, 99.6, 100), (100, 100, 99.6, 100)])  # trades 0.1% through
    assert through.plans == 1 and through.unfilled == 0 and through.equity.iloc[1] != 100_000


def test_gap_below_limit_fills_at_the_open():
    res = run([SETUP_BAR, (99.0, 99.2, 98.9, 99.1), (99, 99, 98, 99)])
    assert res.equity.iloc[1] != 100_000
    assert res.stop_blowthroughs == 0


def test_fees_and_slippage_are_tracked():
    res = run([SETUP_BAR, (100, 100, 98, 99), (99, 110, 96, 100)])
    [t] = res.trades
    assert t.fees > 0 and t.slippage > 0
    assert abs(t.pnl - (t.proceeds - t.cost)) < 1e-9
    assert res.exposure.max() > 0 and res.trade_days
