import pytest

from spot_trd.config import load_universe
from spot_trd.halal_guard import HalalViolation, check_order, check_symbol

U = load_universe()


def test_btc_spot_buy_allowed():
    check_order("BTC/USDT", "spot", "buy", 0.001, 0.0, U)


def test_sell_of_held_btc_allowed():
    check_order("BTC/USDT", "spot", "sell", 0.001, 0.001, U)


@pytest.mark.parametrize(
    "symbol,market_type",
    [
        ("BTC/USDT:USDT", "swap"),      # perpetual future
        ("BTC/USDT:USDT", "spot"),      # derivative symbol mislabeled as spot
        ("BTCUP/USDT", "spot"),         # leveraged token
        ("BTC3L/USDT", "spot"),
        ("BTC/USDT", "margin"),
        ("ETH/USDT", "spot"),           # not on the allowlist yet
    ],
)
def test_blocked(symbol, market_type):
    with pytest.raises(HalalViolation):
        check_symbol(symbol, market_type, U)


def test_short_selling_blocked():
    with pytest.raises(HalalViolation, match="short"):
        check_order("BTC/USDT", "spot", "sell", 0.002, 0.001, U)
