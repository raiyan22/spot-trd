class HalalViolation(Exception):
    pass


def check_symbol(symbol: str, market_type: str, universe: dict) -> None:
    upper = symbol.upper()
    for pattern in universe["blocked_patterns"]:
        if pattern.upper() in upper:
            raise HalalViolation(f"{symbol}: matches blocked pattern '{pattern}' (derivative or leveraged product)")
    if market_type not in universe["allowed_market_types"]:
        raise HalalViolation(f"{symbol}: market type '{market_type}' is not spot")
    if symbol not in universe["allowed_symbols"]:
        raise HalalViolation(f"{symbol}: not on the halal allowlist")


def check_order(symbol: str, market_type: str, side: str, qty: float, held_qty: float, universe: dict) -> None:
    check_symbol(symbol, market_type, universe)
    if side not in ("buy", "sell"):
        raise HalalViolation(f"unknown side '{side}'")
    if qty <= 0:
        raise HalalViolation("order quantity must be positive")
    if side == "sell" and qty > held_qty + 1e-12:
        raise HalalViolation(f"sell {qty} exceeds held {held_qty}: short selling is not allowed")
