import math
from dataclasses import dataclass


@dataclass
class Order:
    price: float
    qty: float

    @property
    def notional(self) -> float:
        return self.price * self.qty


def round_down(qty: float, step: float) -> float:
    return math.floor(qty / step + 1e-9) * step


def risk_pct_for(equity: float, rules: dict) -> float:
    risk = rules["risk"]
    small = risk.get("small_account")
    if small and equity < small["below_equity"]:
        return small["risk_pct"]
    return risk["risk_pct"]


def worst_case_loss(orders: list[Order], stop: float, fee: float, slippage: float) -> float:
    """Loss in USDT if every order fills and the position is stopped out, fees and slippage included."""
    exit_price = stop * (1 - slippage)
    return sum(o.qty * (o.price * (1 + fee) - exit_price * (1 - fee)) for o in orders)


def size_ladder(
    prices: list[float], stop: float, equity: float, cash: float, rules: dict, risk_scale: float = 1.0
) -> tuple[list[Order], str]:
    """Equal-notional ladder whose worst-case loss stays within the risk budget.

    Every buy, and the whole position valued at the stop, must clear Binance's minimum
    notional; otherwise the stop-loss sell itself could be rejected. Tranches are dropped
    (deepest first) until that holds. Returns ([], reason) when no valid ladder exists.
    """
    mkt, risk = rules["market"], rules["risk"]
    fee, slip = mkt["fee_rate"], rules["exit"]["stop_slippage"]
    min_order = mkt["min_notional"] * mkt["notional_buffer"]
    rp = risk_pct_for(equity, rules)
    budget = equity * rp * risk_scale
    if risk_scale <= 0:
        return [], "no risk budget left"
    if any(p <= stop for p in prices):
        return [], "stop is not below every entry"

    for n in range(len(prices), 0, -1):
        ladder = prices[:n]
        loss_per_usdt = sum((p * (1 + fee) - stop * (1 - slip) * (1 - fee)) / p for p in ladder)
        per_order = min(budget / loss_per_usdt, cash * risk["max_cash_use"] / n)
        orders = [Order(p, round_down(per_order / p, mkt["qty_step"])) for p in ladder]
        at_stop = sum(o.qty for o in orders) * stop * (1 - slip)
        if all(o.notional >= min_order for o in orders) and at_stop >= min_order:
            return orders, f"{n} order(s)"
    return [], f"position below Binance minimum ({min_order:.2f} USDT) at {rp:.0%} risk"
