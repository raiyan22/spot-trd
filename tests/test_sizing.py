import copy

import pytest

from spot_trd.config import load_rules
from spot_trd.sizing import risk_pct_for, size_ladder, worst_case_loss

RULES = load_rules()
FEE = RULES["market"]["fee_rate"]
SLIP = RULES["exit"]["stop_slippage"]
MIN_ORDER = RULES["market"]["min_notional"] * RULES["market"]["notional_buffer"]

FLAT_1PCT = copy.deepcopy(RULES)
FLAT_1PCT["risk"]["small_account"] = None


def test_risk_schedule():
    assert risk_pct_for(25, RULES) == 0.02
    assert risk_pct_for(49.99, RULES) == 0.02
    assert risk_pct_for(50, RULES) == 0.01


def test_worst_case_loss_within_budget():
    orders, _ = size_ladder([100_000, 99_000], 96_000, equity=10_000, cash=10_000, rules=RULES)
    assert len(orders) == 2
    loss = worst_case_loss(orders, 96_000, FEE, SLIP)
    assert 0.95 * 100 <= loss <= 100  # 1% of 10,000


def test_small_account_drops_to_single_order():
    # 25 USDT at 1% risk with a ~2% stop: two ~5 USDT orders miss the minimum, one ~10 USDT order fits.
    orders, why = size_ladder([100_000, 99_800], 98_000, equity=25, cash=25, rules=FLAT_1PCT)
    assert len(orders) == 1, why
    assert orders[0].notional >= MIN_ORDER
    assert worst_case_loss(orders, 98_000, FEE, SLIP) <= 25 * 0.01


def test_small_account_uses_2pct_and_keeps_two_orders():
    orders, why = size_ladder([100_000, 99_800], 98_000, equity=25, cash=25, rules=RULES)
    assert len(orders) == 2, why
    assert worst_case_loss(orders, 98_000, FEE, SLIP) <= 25 * 0.02


def test_position_must_clear_minimum_at_stop_price():
    # ~5.6 USDT clears the minimum at entry but not after a 10% fall to the stop, so the stop sell would be rejected.
    orders, why = size_ladder([100_000], 90_000, equity=25, cash=25, rules=RULES)
    assert orders == []
    assert "minimum" in why


def test_cash_cap_limits_position():
    orders, _ = size_ladder([100_000], 99_900, equity=1_000, cash=1_000, rules=RULES)
    assert sum(o.notional for o in orders) <= 1_000 * RULES["risk"]["max_cash_use"] + 1e-6


def test_stop_above_entry_rejected():
    orders, why = size_ladder([100_000], 101_000, equity=1_000, cash=1_000, rules=RULES)
    assert orders == [] and "stop" in why


@pytest.mark.parametrize("equity", [25, 50, 200, 5_000])
def test_risk_never_exceeds_budget(equity):
    orders, _ = size_ladder([60_000, 59_000], 57_500, equity=equity, cash=equity, rules=RULES)
    if orders:
        assert worst_case_loss(orders, 57_500, FEE, SLIP) <= equity * risk_pct_for(equity, RULES) + 1e-9
