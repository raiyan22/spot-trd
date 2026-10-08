import copy

import pandas as pd

from spot_trd.backtest import run_backtest, run_portfolio
from spot_trd.config import load_rules, load_universe

RULES = load_rules()
RULES["exit"].update(tp1_r=None, tp2_r=None, trail_atr_mult=2.0, regime_exit=False, max_hold_days=None)
U = {**load_universe(), "allowed_symbols": ["BTC/USDT", "ETH/USDT", "SOL/USDT"]}
BARS = [(100, 101, 99.8, 100), (100, 100, 98, 99), (99, 106, 99, 105), (105, 112, 105, 111), (111, 111, 107, 108)]


def frame(bars=BARS, signal_day=0):
    idx = pd.date_range("2024-01-01", periods=len(bars), freq="D")
    df = pd.DataFrame(bars, index=idx, columns=["open", "high", "low", "close"], dtype=float)
    df["atr"] = 2.0
    df["signal"] = False
    df.iloc[signal_day, df.columns.get_loc("signal")] = True
    df["trend_ok"] = True
    return df


def test_single_asset_wrapper_matches_portfolio_of_one():
    a = run_backtest(frame(), RULES, U, 100_000, 0.01)
    b = run_portfolio({"BTC/USDT": frame()}, RULES, U, 100_000, 0.01)
    assert a.equity.equals(b.equity) and len(a.trades) == len(b.trades) == 1


def test_position_cap_blocks_second_asset_and_counts_it():
    feats = {"BTC/USDT": frame(), "ETH/USDT": frame()}
    res = run_portfolio(feats, RULES, U, 100_000, 0.01, max_positions=1)
    assert [t.symbol for t in res.trades] == ["BTC/USDT"]       # first asset in order gets the only slot
    assert res.skipped["no free position slot"] == 1 and res.open_positions.max() == 1


def test_equal_slots_split_the_same_total_risk():
    one = run_portfolio({"BTC/USDT": frame()}, RULES, U, 100_000, 0.01, max_positions=1)
    two = run_portfolio({"BTC/USDT": frame(), "ETH/USDT": frame()}, RULES, U, 100_000, 0.01, max_positions=2)
    assert {t.symbol for t in two.trades} == {"BTC/USDT", "ETH/USDT"} and two.open_positions.max() == 2
    total_risk_two = sum(t.risk_usdt for t in two.trades)
    assert abs(total_risk_two - one.trades[0].risk_usdt) / one.trades[0].risk_usdt < 0.02   # same total budget, not 2x
    assert all(t.symbol for t in two.trades) and (two.equity > 0).all()


def test_late_listed_asset_is_ignored_until_it_has_data():
    late = frame(BARS[2:], signal_day=0)
    res = run_portfolio({"BTC/USDT": frame(), "SOL/USDT": late}, RULES, U, 100_000, 0.01, max_positions=2)
    assert len(res.equity) == 5 and (res.equity > 0).all()


def test_stop_fill_slippage_can_exceed_sizing_assumption():
    rules = copy.deepcopy(RULES)
    bars = [(100, 101, 99.8, 100), (100, 100, 98, 99), (99, 99, 90, 91)]       # stopped out on day 3
    base = run_backtest(frame(bars), rules, U, 100_000, 0.01).trades[0]
    rules["execution"] = {"stop_fill_slippage": 0.01}
    stressed = run_backtest(frame(bars), rules, U, 100_000, 0.01).trades[0]
    assert -1.05 < base.r_multiple < -0.95 and stressed.r_multiple < base.r_multiple - 0.1
    assert stressed.risk_usdt == base.risk_usdt                                  # planned risk is unchanged


def test_alternative_entry_modes_change_only_how_the_position_is_bought():
    bars = [(100, 101, 99.8, 100), (100, 100, 98, 99), (99, 106, 99, 105), (105, 112, 105, 111), (111, 111, 107, 108)]
    f = frame(bars)
    lad = run_portfolio({"BTC/USDT": f}, RULES, U, 100_000, 0.01)
    mkt = run_portfolio({"BTC/USDT": f}, RULES, U, 100_000, 0.01, entry_mode="market")
    one = run_portfolio({"BTC/USDT": f}, RULES, U, 100_000, 0.01, entry_mode="single_limit")
    assert lad.plan_dates == mkt.plan_dates == one.plan_dates == [f.index[0]]          # same signal, one plan each
    assert mkt.trades[0].entry_date == f.index[1]                                        # market: the next open
    assert abs(mkt.trades[0].avg_entry - 100 * 1.001 * 1.001) < 0.2                      # open + slippage + fee
    assert one.trades[0].avg_entry <= 99.0 * 1.001 + 1e-6                                # limit at close - 0.5 ATR = 99
    assert lad.trades[0].exit_date == mkt.trades[0].exit_date == one.trades[0].exit_date
