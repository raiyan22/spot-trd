import copy
from collections import Counter
from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd

from spot_trd.risk import CircuitBreaker
from spot_trd.sizing import Order, round_down, size_ladder, worst_case_loss
from spot_trd.strategy import Plan, make_plan

# Daily-bar execution assumptions (audit 2026-10-02). Used when rules["execution"] omits a key, so a missing
# config can never silently fall back to optimistic fills.
EXECUTION_DEFAULTS = {
    "limit_penetration": 0.0005,   # a resting limit buy fills only if the low trades this far BELOW it
    "exit_at_next_open": True,     # decisions made on a daily close (regime/time exits, market entries) fill next open
    "exit_slippage": 0.001,        # adverse slippage on those next-open market fills
    "stop_fill_slippage": None,    # stop fills' slippage when it should differ from the sizing assumption (stress tests)
}


@dataclass
class Trade:
    plan_date: pd.Timestamp
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    qty: float
    avg_entry: float
    cost: float
    proceeds: float
    risk_usdt: float
    exit_reason: str
    equity_after: float        # total account equity right after the exit
    fees: float = 0.0          # USDT paid in exchange fees, both sides
    slippage: float = 0.0      # USDT lost versus the intended fill price (market-type fills and stops)
    stop_level: float = 0.0    # the stop price in force when the trade closed
    symbol: str = ""

    @property
    def pnl(self) -> float:
        return self.proceeds - self.cost

    @property
    def r_multiple(self) -> float:
        return self.pnl / self.risk_usdt if self.risk_usdt > 0 else 0.0


@dataclass
class _Position:
    plan: Plan
    entry_i: int
    entry_date: pd.Timestamp
    stop: float
    high: float
    stop_kind: str = "stop"
    cost: float = 0.0
    proceeds: float = 0.0
    qty_bought: float = 0.0
    risk_usdt: float = 0.0
    tp1_done: bool = False
    fees: float = 0.0
    slippage: float = 0.0
    exit_next: str | None = None   # reason for a market exit to execute at the next open


@dataclass
class Result:
    initial: float
    trades: list[Trade]
    equity: pd.Series
    in_market: pd.Series
    plans: int = 0
    unfilled: int = 0
    skipped: Counter = field(default_factory=Counter)
    halts: list[tuple[pd.Timestamp, str]] = field(default_factory=list)
    exposure: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))     # position value / equity, per day
    trade_days: set = field(default_factory=set)                                      # days with any fill or exit
    stop_blowthroughs: int = 0   # stop exits where the day's low pierced the stop-limit's limit price
    open_positions: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))  # concurrent positions, per day
    signals: int = 0             # entry signals seen while the asset was flat and the breaker was off
    extra_fees: float = 0.0      # fees/slippage not attached to a Trade (e.g. a buy-and-hold core that never closes)
    extra_slippage: float = 0.0
    plan_dates: list = field(default_factory=list)   # signal dates of every plan issued (filled or not)


class _Account:
    """Cash and the circuit breaker are shared by every asset in a run."""

    def __init__(self, initial: float, risk_cfg: dict):
        self.cash = initial
        self.breaker = CircuitBreaker(risk_cfg, initial)
        self.assets: list["_Asset"] = []

    def equity(self, i: int) -> float:
        return self.cash + sum(a.value(i) for a in self.assets)

    def reserved(self) -> float:
        return sum(a.reserved() for a in self.assets)


class _Asset:
    """One symbol's order, position and exit state machine (the per-bar logic of the original single-asset backtest)."""

    def __init__(self, symbol: str, feat: pd.DataFrame, rules: dict, index: pd.DatetimeIndex):
        self.symbol, self.rules = symbol, rules
        f = feat.reindex(index)
        self.feat = f
        self.o, self.h, self.l, self.c, self.atr = (f[k].to_numpy() for k in ("open", "high", "low", "close", "atr"))
        self.signals = f["signal"].fillna(False).to_numpy(dtype=bool)
        self.trend_ok = f["trend_ok"].fillna(False).to_numpy(dtype=bool)
        self.donchian_trail = rules["exit"].get("trail_mode") == "donchian_mid"
        self.dc_mid = f["dc_mid"].to_numpy() if self.donchian_trail else None
        self.pending: list[Order] = []
        self.plan: Plan | None = None
        self.expiry_i = -1
        self.pos: _Position | None = None
        self.qty = 0.0

    def value(self, i: int) -> float:
        return self.qty * self.c[i] if self.qty > 0 and not np.isnan(self.c[i]) else 0.0

    def reserved(self) -> float:
        fee = self.rules["market"]["fee_rate"]
        return sum(o.notional * (1 + fee) for o in self.pending)

    # -- fills ---------------------------------------------------------------------------------------------------
    def _sell(self, acct: _Account, q: float, px: float, ref: float) -> None:
        """Sell q at px; ref is the intended price, so (ref - px) is slippage."""
        fee = self.rules["market"]["fee_rate"]
        acct.cash += q * px * (1 - fee)
        self.pos.proceeds += q * px * (1 - fee)
        self.pos.fees += q * px * fee
        self.pos.slippage += q * max(ref - px, 0.0)
        self.qty = 0.0 if q >= self.qty else self.qty - q

    def _close(self, acct: _Account, res: Result, i: int, reason: str) -> None:
        pos = self.pos
        self.pending = []
        idx = self.feat.index
        eq = acct.equity(i)
        trade = Trade(self.plan.date, pos.entry_date, idx[i], pos.qty_bought, pos.cost / pos.qty_bought, pos.cost,
                      pos.proceeds, pos.risk_usdt, reason, eq, pos.fees, pos.slippage, pos.stop, self.symbol)
        res.trades.append(trade)
        res.trade_days.add(idx[i])
        self.pos = None
        acct.breaker.on_trade_closed(idx[i], trade.pnl, eq)

    # -- one bar -------------------------------------------------------------------------------------------------
    def process(self, i: int, acct: _Account, res: Result, x: dict) -> None:
        o, h, l, c = self.o[i], self.h[i], self.l[i], self.c[i]
        if np.isnan(o):
            return  # not listed yet
        rules, mkt, ex = self.rules, self.rules["market"], self.rules["exit"]
        fee, slip = mkt["fee_rate"], ex["stop_slippage"]
        fill_slip = x["stop_fill_slippage"] if x["stop_fill_slippage"] is not None else slip
        pen, exit_slip = x["limit_penetration"], x["exit_slippage"]
        step, min_sell = mkt["qty_step"], mkt["min_notional"]
        min_keep = mkt["min_notional"] * mkt["notional_buffer"]
        idx = self.feat.index
        filled_today = False

        # A market exit decided at yesterday's close executes now, at today's open.
        if self.pos is not None and self.pos.exit_next and self.qty > 0:
            gap_stop = o <= self.pos.stop  # already through the stop at the open: the stop's slippage applies
            self._sell(acct, self.qty, o * (1 - (fill_slip if gap_stop else exit_slip)), o)
            self._close(acct, res, i, self.pos.exit_next)

        if self.pending:
            still = []
            for od in self.pending:
                if self.plan.market or o <= od.price or l <= od.price * (1 - pen):
                    ref = o if self.plan.market else min(od.price, o)
                    px = o * (1 + exit_slip) if self.plan.market else ref
                    cost = od.qty * px * (1 + fee)
                    acct.cash -= cost
                    self.qty += od.qty
                    if self.pos is None:
                        self.pos = _Position(self.plan, i, idx[i], self.plan.stop, high=px)
                    pos = self.pos
                    pos.cost += cost
                    pos.qty_bought += od.qty
                    pos.fees += od.qty * px * fee
                    pos.slippage += od.qty * (px - ref)
                    pos.risk_usdt += od.qty * (px * (1 + fee) - self.plan.stop * (1 - slip) * (1 - fee))
                    filled_today = True
                    res.trade_days.add(idx[i])
                else:
                    still.append(od)
            self.pending = still

        pos = self.pos
        if pos is not None and self.qty > 0:
            plan, reason = self.plan, None
            if l <= pos.stop:
                if l < pos.stop * (1 - ex["stop_limit_offset"]):
                    res.stop_blowthroughs += 1
                px = min(pos.stop, o)
                self._sell(acct, self.qty, px * (1 - fill_slip), px)
                reason = pos.stop_kind
            elif not filled_today:
                if plan.tp1 is not None and not pos.tp1_done and h >= plan.tp1:
                    piece = round_down(self.qty * ex["tp1_fraction"], step)
                    breakeven = pos.cost / pos.qty_bought / ((1 - fee) * (1 - slip))
                    can_split = piece * plan.tp1 >= min_sell and (self.qty - piece) * breakeven >= min_keep
                    px = max(plan.tp1, o)
                    self._sell(acct, piece if can_split else self.qty, px, px)
                    pos.tp1_done = True
                    self.pending = []
                    if breakeven > pos.stop:
                        pos.stop, pos.stop_kind = breakeven, "breakeven"
                    if self.qty == 0:
                        reason = "tp1"
                if plan.tp2 is not None and self.qty > 0 and (pos.tp1_done or plan.tp1 is None) and h >= plan.tp2:
                    px = max(plan.tp2, o)
                    self._sell(acct, self.qty, px, px)
                    reason = "tp2"
            if reason is None and self.qty > 0:
                why = None
                if ex["max_hold_days"] and i - pos.entry_i >= ex["max_hold_days"]:
                    why = "time"
                elif ex["regime_exit"] and not self.trend_ok[i]:
                    why = "regime"
                if why:
                    if x["exit_at_next_open"] and i + 1 < len(idx):
                        pos.exit_next = why   # known only at this close; the sell happens next open
                        self.pending = []
                    else:
                        self._sell(acct, self.qty, c * (1 - exit_slip), c)
                        reason = why
            if reason is None and self.qty > 0 and (ex["trail_atr_mult"] or self.donchian_trail):
                if self.donchian_trail:
                    trail = self.dc_mid[i]
                else:
                    # Fill-bar highs may precede the fill, so only the close counts on that bar.
                    pos.high = max(pos.high, c if filled_today else h)
                    trail = pos.high - ex["trail_atr_mult"] * self.atr[i]
                if trail > pos.stop:
                    pos.stop, pos.stop_kind = trail, "trail"
            if reason is not None:
                self._close(acct, res, i, reason)

        if self.pending and i >= self.expiry_i:
            self.pending = []
            if self.pos is None:
                res.unfilled += 1


def _alternative_entry(plan, row, rules, equity, cash, scale, mode):
    """Execution-only variants of v2's entry (research diagnostic). The signal, the stop level, the exits and the risk budget are
    unchanged; only how the position is bought differs. 'market': one market buy at the next open. 'single_limit': one limit
    buy at the average of the ladder prices."""
    ladder = [row["close"] - k * row["atr"] for k in rules["entry"]["ladder_atr_offsets"]]
    ref = row["close"] if mode == "market" else float(np.mean(ladder))
    if mode not in ("market", "single_limit"):
        raise ValueError(mode)
    orders, why = size_ladder([ref], plan.stop, equity, cash, rules, scale)
    if not orders:
        return None, why
    risk = worst_case_loss(orders, plan.stop, rules["market"]["fee_rate"], rules["exit"]["stop_slippage"])
    return replace(plan, orders=orders, market=(mode == "market"), valid_days=1 if mode == "market" else plan.valid_days,
                   risk_usdt=risk), why


def run_portfolio(
    feats: dict[str, pd.DataFrame],
    rules: dict,
    universe: dict,
    initial_capital: float | None = None,
    risk_pct: float | None = None,
    max_positions: int = 1,
    allocation: str = "equal",
    asset_rules: dict[str, dict] | None = None,
    entry_mode: str = "ladder",
) -> Result:
    """Daily-bar simulation over one or more assets sharing one account. Within a bar the stop is always assumed to
    trigger before any target.

    Conservative execution: a signal is known only at a bar's close, so market-type exits fill at the NEXT open with
    slippage; resting limit buys fill only when price trades through the limit; stops fill at min(stop, open) less
    slippage. risk_pct, when given, overrides the risk schedule with a flat percentage.

    Portfolio risk: the per-trade risk budget of the single-asset system is the TOTAL budget for the account.
    allocation="equal" gives each of the max_positions slots 1/max_positions of it; "heat" lets a new position use
    whatever budget is left after the open positions' current risk-to-stop. Assets are served in the order given.
    asset_rules maps a symbol to market overrides (qty_step, min_notional).
    """
    rules = copy.deepcopy(rules)
    if risk_pct is not None:
        rules["risk"]["risk_pct"] = risk_pct
        rules["risk"]["small_account"] = None
    x = {**EXECUTION_DEFAULTS, **rules.get("execution", {})}
    initial = initial_capital if initial_capital is not None else rules["account"]["initial_capital"]
    idx = sorted(set().union(*[f.index for f in feats.values()]))
    idx = pd.DatetimeIndex(idx)

    acct = _Account(initial, rules["risk"])
    for sym, f in feats.items():
        r = copy.deepcopy(rules)
        r["market"].update((asset_rules or {}).get(sym, {}))
        r["market"]["symbol"] = sym
        acct.assets.append(_Asset(sym, f, r, idx))

    res = Result(initial, [], pd.Series(dtype=float), pd.Series(dtype=bool))
    equity, in_market, exposure, n_open = [], [], [], []
    from spot_trd.sizing import risk_pct_for

    for i in range(len(idx)):
        for a in acct.assets:
            a.process(i, acct, res, x)

        # New plans, in asset order, while slots are free and the breaker allows.
        used = sum(1 for a in acct.assets if a.pos is not None or a.pending)
        for a in acct.assets:
            if a.pos is not None or a.pending or not a.signals[i] or acct.breaker.halted(idx[i]):
                continue
            res.signals += 1
            if used >= max_positions:
                res.skipped["no free position slot"] += 1
                continue
            eq = acct.equity(i)
            avail = acct.cash - acct.reserved()
            scale = 1.0 / max_positions
            if allocation == "heat":
                budget = eq * risk_pct_for(eq, a.rules)
                open_risk = sum(max(b.qty * (b.c[i] - b.pos.stop), 0.0) for b in acct.assets if b.pos is not None)
                scale = max(budget - open_risk, 0.0) / budget
            plan, why = make_plan(a.feat.iloc[i], eq, avail, a.rules, universe, symbol=a.symbol, risk_scale=scale)
            if plan is not None and entry_mode != "ladder":
                plan, why = _alternative_entry(plan, a.feat.iloc[i], a.rules, eq, avail, scale, entry_mode)
            if plan is None:
                res.skipped[why] += 1
            else:
                a.plan, a.pending, a.expiry_i = plan, list(plan.orders), i + plan.valid_days
                res.plans += 1
                res.plan_dates.append(idx[i])
                used += 1

        eq = acct.equity(i)
        equity.append(eq)
        held = [a for a in acct.assets if a.qty > 0]
        in_market.append(bool(held))
        n_open.append(len(held))
        exposure.append(sum(a.value(i) for a in held) / eq if eq > 0 else 0.0)

    res.equity = pd.Series(equity, index=idx)
    res.in_market = pd.Series(in_market, index=idx)
    res.exposure = pd.Series(exposure, index=idx)
    res.open_positions = pd.Series(n_open, index=idx)
    res.halts = acct.breaker.events
    return res


def run_backtest(
    feat: pd.DataFrame,
    rules: dict,
    universe: dict,
    initial_capital: float | None = None,
    risk_pct: float | None = None,
) -> Result:
    """Single-asset backtest of rules["market"]["symbol"] (see run_portfolio)."""
    return run_portfolio({rules["market"]["symbol"]: feat}, rules, universe, initial_capital, risk_pct)
