from dataclasses import dataclass

import pandas as pd

from spot_trd.halal_guard import check_symbol
from spot_trd.sizing import Order, size_ladder, worst_case_loss


@dataclass
class Plan:
    date: pd.Timestamp
    orders: list[Order]
    market: bool          # True: buy at the next open; False: resting limit orders
    stop: float
    tp1: float | None
    tp2: float | None
    risk_usdt: float
    valid_days: int

    @property
    def avg_entry(self) -> float:
        return sum(o.notional for o in self.orders) / sum(o.qty for o in self.orders)


def make_plan(row: pd.Series, equity: float, cash: float, rules: dict, universe: dict,
              symbol: str | None = None, risk_scale: float = 1.0) -> tuple[Plan | None, str]:
    """Build an entry plan from a signal bar, or explain why there is none.

    risk_scale < 1 takes only that fraction of the normal per-trade risk budget (portfolio slots)."""
    check_symbol(symbol or rules["market"]["symbol"], "spot", universe)
    if not row["signal"]:
        return None, "no signal"

    ex = rules["exit"]
    market = rules["strategy"] == "trend"
    if market:
        prices = [row["close"]]
    else:
        prices = [row["close"] - k * row["atr"] for k in rules["entry"]["ladder_atr_offsets"]]
    stop = min(prices) - ex["stop_atr_mult"] * row["atr"]
    orders, reason = size_ladder(prices, stop, equity, cash, rules, risk_scale)
    if not orders:
        return None, reason

    avg = sum(o.notional for o in orders) / sum(o.qty for o in orders)
    r = avg - stop
    plan = Plan(
        date=row.name,
        orders=orders,
        market=market,
        stop=stop,
        tp1=avg + ex["tp1_r"] * r if ex["tp1_r"] else None,
        tp2=avg + ex["tp2_r"] * r if ex["tp2_r"] else None,
        risk_usdt=worst_case_loss(orders, stop, rules["market"]["fee_rate"], ex["stop_slippage"]),
        valid_days=1 if market else rules["entry"]["valid_days"],
    )
    return plan, reason
