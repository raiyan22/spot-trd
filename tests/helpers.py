import pandas as pd

LAST_DAY = pd.Timestamp("2026-09-30")


def make_feat(n=30, close=100_000.0, atr=2_000.0, signal=True, trend_ok=True):
    idx = pd.date_range(end=LAST_DAY, periods=n, freq="D")
    f = pd.DataFrame(index=idx)
    f["open"] = f["close"] = close
    f["high"], f["low"] = close * 1.01, close * 0.99
    f["ema_pb"], f["ema_fast"], f["ema_slow"] = close, close * 0.95, close * 0.9
    f["rsi"], f["atr"] = 50.0, atr
    for col in ("monthly_up", "daily_up", "trend_ok", "regime_ok"):
        f[col] = trend_ok
    for col in ("spx_weak", "dxy_surge", "commodity_stress", "risk_off"):
        f[col] = False
    f["pullback"] = f["setup"] = f["signal"] = signal
    return f
