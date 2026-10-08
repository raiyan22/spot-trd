import numpy as np
import pandas as pd

from spot_trd.intraday import (COSTS, Signals, build_signals, day_gate, perturb_h1, run_all, simulate)


def synthetic(days=120, seed=2):
    rng = np.random.default_rng(seed)
    n = 24 * days
    close = 30_000 * np.exp(np.cumsum(rng.normal(0, 0.006, n)))
    idx = pd.date_range("2022-01-01", periods=n, freq="h")
    open_ = np.r_[close[0], close[:-1]]
    hi = np.maximum(open_, close) * (1 + rng.uniform(0, 0.004, n))
    lo = np.minimum(open_, close) * (1 - rng.uniform(0, 0.004, n))
    return pd.DataFrame({"open": open_, "high": hi, "low": lo, "close": close}, index=idx)


def flat_sig(n):
    return Signals(np.zeros(n, bool), np.full(n, np.nan), np.full(n, np.nan), np.zeros(n, bool))


def test_no_signal_means_no_trade_and_flat_equity():
    h1 = synthetic()
    res = simulate(h1, flat_sig(len(h1)), COSTS["base"], 300.0)
    assert res["trades"] == [] and (res["equity"] == 300.0).all()


def test_entry_is_next_open_with_slippage_and_exit_by_2300():
    h1 = synthetic(10)
    sig = flat_sig(len(h1))
    i = 24 * 3 + 6                                             # decided at the close of the 06:00 candle on day 4
    sig.sig[i], sig.stop[i] = True, h1["close"].iloc[i] * 0.80  # stop far away
    res = simulate(h1, sig, COSTS["base"], 100_000.0)
    [t] = res["trades"]
    assert t.entry_time == h1.index[i + 1]
    assert abs(t.entry_px - h1["open"].iloc[i + 1] * 1.0005) < 1e-6 or abs(t.entry_px - h1["open"].iloc[i + 1]) < 1e-6
    assert t.exit_time.hour == 23 and t.exit_time.date() == t.entry_time.date() and t.reason == "time"
    assert t.fees > 0 and t.gross - t.ret > 0.0019            # at least the two fees come off the move


def test_stop_beats_target_inside_the_same_candle_and_gap_fills_at_open():
    idx = pd.date_range("2022-01-03", periods=30, freq="h")
    base = 100.0
    df = pd.DataFrame({"open": base, "high": base, "low": base, "close": base}, index=idx)
    df.iloc[7] = [100, 103, 96, 100]                          # entry candle: touches both target 102 and stop 97
    sig = flat_sig(len(df))
    sig.sig[6], sig.stop[6], sig.target[6] = True, 97.0, 102.0
    [t] = simulate(df, sig, COSTS["base"], 100_000.0)["trades"]
    assert t.reason == "stop" and t.exit_px < 97
    df2 = df.copy()
    df2.iloc[7] = [100, 100, 100, 100]
    df2.iloc[8] = [94, 95, 93, 94]                            # gaps below the stop at the open
    [t2] = simulate(df2, sig, COSTS["base"], 100_000.0)["trades"]
    assert t2.reason == "stop" and abs(t2.exit_px - 94 * (1 - 0.001)) < 1e-9


def test_one_entry_per_day_and_never_held_overnight():
    h1 = synthetic(60)
    sig = flat_sig(len(h1))
    hours = h1.index.hour
    sig.sig[:] = (hours >= 2) & (hours <= 19)                  # a signal on almost every candle
    sig.stop[:] = h1["close"].to_numpy() * 0.5
    res = simulate(h1, sig, COSTS["base"], 100_000.0)
    days = [t.entry_time.date() for t in res["trades"]]
    assert len(days) == len(set(days)) and len(days) >= 50
    assert all(t.exit_time.date() == t.entry_time.date() for t in res["trades"])
    assert all(1 <= t.entry_time.hour <= 20 for t in res["trades"])


def test_position_below_binance_minimum_is_skipped_not_scaled_up():
    h1 = synthetic(10)
    sig = flat_sig(len(h1))
    sig.sig[24 * 3 + 6], sig.stop[24 * 3 + 6] = True, h1["close"].iloc[24 * 3 + 6] * 0.99
    res = simulate(h1, sig, COSTS["base"], 3.0)               # $3 account cannot reach the 5.5 USDT minimum
    assert res["trades"] == [] and res["skipped"] == 1


def test_harsh_costs_never_beat_base_costs_on_identical_signals():
    h1 = synthetic(200, seed=5)
    gates = {"B": np.ones(len(h1), bool), "C": np.ones(len(h1), bool)}
    b, h = run_all(h1, gates, COSTS["base"], 100_000.0), run_all(h1, gates, COSTS["harsh"], 100_000.0)
    for k in "ABC":
        assert sum(t.pnl for t in h[k]["trades"]) <= sum(t.pnl for t in b[k]["trades"]) + 1e-6


def test_future_candles_cannot_change_past_trades():
    h1 = synthetic(150, seed=7)
    cut = h1.index[24 * 100]
    other = perturb_h1(h1, cut, 3)
    assert not np.allclose(h1["close"].iloc[-20:], other["close"].iloc[-20:])
    gates = {"B": np.ones(len(h1), bool), "C": np.ones(len(h1), bool)}
    a, b = run_all(h1, gates, COSTS["base"], 100_000.0), run_all(other, gates, COSTS["base"], 100_000.0)
    for k in "ABC":
        ta = [(t.entry_time, t.exit_time, round(t.ret, 12)) for t in a[k]["trades"] if t.exit_time <= cut]
        tb = [(t.entry_time, t.exit_time, round(t.ret, 12)) for t in b[k]["trades"] if t.exit_time <= cut]
        assert ta == tb


def test_a_leaked_signal_is_visibly_better():
    h1 = synthetic(300, seed=9)
    gates = {"B": np.ones(len(h1), bool), "C": np.ones(len(h1), bool)}
    ok = run_all(h1, gates, COSTS["base"], 100_000.0)
    leak = run_all(h1, gates, COSTS["base"], 100_000.0, leak=True)
    wins = 0
    for k in "ABC":
        if ok[k]["trades"] and leak[k]["trades"]:
            wins += np.mean([t.ret for t in leak[k]["trades"]]) > np.mean([t.ret for t in ok[k]["trades"]]) + 0.001
    assert wins >= 2


def test_daily_gate_uses_only_the_previous_completed_day():
    idx = pd.date_range("2022-01-01", periods=24 * 5, freq="h")
    daily = pd.Series([False, False, True, False, False], index=pd.date_range("2022-01-01", periods=5, freq="D"))
    g = day_gate(daily, idx)
    assert not g[:72].any() and g[72:96].all() and not g[96:].any()   # day 3's True first applies on day 4


def test_opening_range_signal_waits_for_the_range_to_complete():
    idx = pd.date_range("2022-01-03", periods=48, freq="h")
    df = pd.DataFrame({"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0}, index=idx)
    df.iloc[2] = [100, 110, 99, 109]                          # a 02:00 spike must not trigger anything (range not complete)
    df.iloc[5] = [100, 112, 100, 111]                         # 05:00 closes above the 00:00-03:59 high (110)
    s = build_signals(df, "A")
    assert not s.sig[:5].any() and s.sig[5] and s.sig.sum() == 1 and s.stop[5] == 99.0
