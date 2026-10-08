import numpy as np
import pandas as pd

from spot_trd.backtest import run_backtest
from spot_trd.challengers import SMA_DAYS, combine, perturb, run_hold, trend_target
from spot_trd.config import load_rules, load_universe

RULES = load_rules()
U = load_universe()


def synthetic(n=900, seed=1):
    rng = np.random.default_rng(seed)
    close = 20_000 * np.exp(np.cumsum(rng.normal(0.0008, 0.03, n)))
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    open_ = np.r_[close[0], close[:-1]] * (1 + rng.normal(0, 0.002, n))
    hi = np.maximum(open_, close) * 1.01
    lo = np.minimum(open_, close) * 0.99
    return pd.DataFrame({"open": open_, "high": hi, "low": lo, "close": close}, index=idx)


def test_sma_uses_only_trailing_closes():
    btc = synthetic()
    tgt = trend_target(btc, btc.index)
    sma = btc["close"].rolling(SMA_DAYS).mean()
    for k in (250, 400, 899):
        assert np.isclose(sma.iloc[k], btc["close"].iloc[k - SMA_DAYS + 1:k + 1].mean())
    assert not tgt.iloc[:SMA_DAYS - 1].any()           # no signal before 200 closes exist


def test_future_prices_cannot_change_past_equity():
    btc = synthetic()
    cut = btc.index[600]
    other = perturb(btc, cut, 7)
    assert not np.allclose(btc["close"].iloc[-50:], other["close"].iloc[-50:])
    for exposure in (1.0, 0.25):
        a = run_hold(btc, trend_target(btc, btc.index), 1000.0, RULES, 0.001, 0.001, exposure).equity
        b = run_hold(other, trend_target(other, other.index), 1000.0, RULES, 0.001, 0.001, exposure).equity
        assert np.allclose(a[a.index <= cut], b[b.index <= cut], rtol=1e-9)


def test_leaked_signal_is_visibly_better_than_correct_one():
    btc = synthetic(1500, seed=4)
    tgt = trend_target(btc, btc.index)
    ok = run_hold(btc, tgt, 1000.0, RULES, 0.001, 0.001).equity.iloc[-1]
    leak = run_hold(btc, tgt, 1000.0, RULES, 0.001, 0.001, lag=0).equity.iloc[-1]
    assert leak > 1.3 * ok


def test_no_rebalancing_between_entry_and_exit():
    btc = synthetic()
    res = run_hold(btc, trend_target(btc, btc.index), 1000.0, RULES, 0.001, 0.001, 0.25)
    assert res.trades
    for t in res.trades:
        seg = res.equity[(res.equity.index >= t.entry_date) & (res.equity.index < t.exit_date)]
        flat_before = res.equity[res.equity.index < t.entry_date]
        cash0 = (flat_before.iloc[-1] if len(flat_before) else 1000.0) - t.cost
        qty = (seg - cash0) / btc["close"].reindex(seg.index)
        assert np.allclose(qty, t.qty, rtol=1e-9)
    assert abs(res.trades[0].cost - 250 * 1.0) < 5          # exposure applied once, to cash at entry


def test_position_below_binance_minimum_is_not_scaled_up():
    btc = synthetic()
    res = run_hold(btc, trend_target(btc, btc.index), 20.0, RULES, 0.001, 0.001, 0.10)    # 10% of $20 = $2 < $5.5
    assert res.trades == [] and res.skipped["position below Binance minimum"] >= 1
    assert (res.equity == 20.0).all()


def test_entry_fills_at_next_open_with_slippage_and_fee():
    btc = synthetic()
    tgt = trend_target(btc, btc.index)
    res = run_hold(btc, tgt, 1000.0, RULES, 0.002, 0.001, 1.0)
    t = res.trades[0]
    first_on = tgt[tgt].index[0]
    assert t.entry_date == first_on + pd.Timedelta(days=1)
    px = btc.loc[t.entry_date, "open"] * 1.002
    assert abs(t.cost / t.qty - px * 1.001) < 1e-6


def test_combined_core_and_tactical_adds_up():
    btc = synthetic()
    f = btc.assign(atr=btc["close"] * 0.03, signal=False, trend_ok=True)
    core = run_hold(f, pd.Series(True, index=f.index), 250.0, RULES, 0.001, 0.001, 1.0, mark_open=False)
    tact = run_backtest(f, RULES, U, 750.0)
    both = combine(core, tact, 1000.0)
    assert np.allclose(both.equity, core.equity + tact.equity) and both.extra_fees == core.extra_fees > 0
