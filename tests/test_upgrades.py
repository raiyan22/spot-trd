import copy

import pandas as pd
import pytest

from spot_trd.backtest import run_backtest
from spot_trd.config import load_rules, load_universe
from spot_trd.regime import entry_filters

RULES, U = load_rules(), load_universe()
IDX = pd.date_range("2024-01-01", periods=4, freq="D")


def with_filters(**flt):
    r = copy.deepcopy(RULES)
    r["filters"] = flt
    return r


def test_no_filters_means_no_veto():
    assert entry_filters(pd.DataFrame(index=IDX), RULES, None).all()


def test_filters_need_external_data():
    with pytest.raises(ValueError, match="external data"):
        entry_filters(pd.DataFrame(index=IDX), with_filters(fng_block_at=75), None)


def test_fear_greed_and_mvrv_vetoes():
    ext = pd.DataFrame({"fng": [20, 50, 75, 90], "mvrv": [1.0, 2.0, 3.0, 1.5]}, index=IDX)
    f = pd.DataFrame(index=IDX)
    assert entry_filters(f, with_filters(fng_block_at=75), ext).tolist() == [True, True, False, False]
    assert entry_filters(f, with_filters(fng_entry_max=50), ext).tolist() == [True, True, False, False]
    assert entry_filters(f, with_filters(mvrv_block_at=3.0), ext).tolist() == [True, True, False, True]


def test_donchian_midpoint_trailing_exit():
    rules = copy.deepcopy(RULES)
    rules["exit"].update(trail_mode="donchian_mid", tp1_r=None, tp2_r=None, max_hold_days=None, regime_exit=False)
    bars = [(100, 101, 99.8, 100), (100, 100, 98, 99), (99, 106, 99, 105), (105, 106, 101, 102)]
    f = pd.DataFrame(bars, index=IDX, columns=["open", "high", "low", "close"], dtype=float)
    f["atr"], f["signal"], f["trend_ok"] = 2.0, [True, False, False, False], True
    f["dc_mid"] = [None, None, 102.5, 103.0]  # midpoint rises above entry; day 4's low of 101 breaks 102.5
    [t] = run_backtest(f, rules, U, initial_capital=100_000, risk_pct=0.01).trades
    assert t.exit_reason == "trail" and t.exit_date == IDX[3]
