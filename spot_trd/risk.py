import pandas as pd


class CircuitBreaker:
    """Pauses new entries after a losing streak or a drawdown from peak equity."""

    def __init__(self, risk_cfg: dict, equity: float):
        self.cfg = risk_cfg
        self.peak = equity
        self.losses = 0
        self.halt_until: pd.Timestamp | None = None
        self.events: list[tuple[pd.Timestamp, str]] = []

    def _halt(self, when: pd.Timestamp, days: int, why: str) -> None:
        until = when + pd.Timedelta(days=days)
        if self.halt_until is None or until > self.halt_until:
            self.halt_until = until
        self.events.append((when, f"{why}: pause {days}d"))

    def on_deposit(self, equity: float) -> None:
        self.peak = max(self.peak, equity)

    def on_trade_closed(self, when: pd.Timestamp, pnl: float, equity: float) -> None:
        cfg = self.cfg
        self.losses = self.losses + 1 if pnl < 0 else 0
        if self.losses >= cfg["max_consecutive_losses"]:
            self._halt(when, cfg["streak_pause_days"], f"{self.losses} losses in a row")
            self.losses = 0
        self.peak = max(self.peak, equity)
        if equity < self.peak * (1 - cfg["floor_pct"]):
            self._halt(
                when, cfg["halt_pause_days"],
                f"equity {equity:.2f} fell >{cfg['floor_pct']:.0%} below peak {self.peak:.2f}",
            )
            self.peak = equity

    def halted(self, when: pd.Timestamp) -> bool:
        return self.halt_until is not None and when < self.halt_until
