import numpy as np

from spot_trd.capital import sim_contrib, state, usd


def test_deposits_are_never_counted_as_profit():
    zero = [(np.zeros(5), 6.0)] * 3                     # every trade returns exactly 0%
    T, E = sim_contrib(zero, 25.0, 50.0, 4.25, n=500, seed=1)
    for t in (0.5, 1.0, 2.7, 3.25, 4.25):
        eq, pnl = state(T, E, 25.0, 50.0, t)
        assert np.allclose(eq, 25.0 + 50.0 * np.floor(t))   # account value is exactly what was put in
        assert np.allclose(pnl, 0.0)                        # so trading profit is exactly zero


def test_without_additions_equity_follows_trades_only():
    up = [(np.full(5, 0.01), 6.0)] * 3
    T, E = sim_contrib(up, 300.0, 0.0, 3.0, n=300, seed=2)
    eq, pnl = state(T, E, 300.0, 0.0, 3.0)
    n_trades = (T <= 3.0).sum(axis=1)
    assert np.allclose(eq, 300.0 * 1.01 ** n_trades) and (pnl >= 0).all()


def test_first_deposit_comes_on_the_first_anniversary():
    zero = [(np.zeros(5), 0.5)] * 3                    # almost no trades
    T, E = sim_contrib(zero, 100.0, 100.0, 4.25, n=100, seed=3)
    eq_before, _ = state(T, E, 100.0, 100.0, 0.99)
    eq_after, _ = state(T, E, 100.0, 100.0, 1.0)
    assert np.allclose(eq_before, 100.0) and np.allclose(eq_after, 200.0)


def test_money_format():
    assert usd(49.4) == "+$49" and usd(-3.2) == "-$3"
