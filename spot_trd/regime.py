import pandas as pd

from spot_trd.indicators import atr, ema, rsi, sma


def monthly_uptrend(close: pd.Series, n: int) -> pd.Series:
    monthly = close.resample("ME").last()
    up = monthly > sma(monthly, n)
    # Month-end labels mean a month's verdict only applies from its final daily close onward.
    return up.reindex(close.index, method="ffill").fillna(False).astype(bool)


def macro_flags(macro: pd.DataFrame, cfg: dict, index: pd.DatetimeIndex) -> pd.DataFrame:
    spx, dxy = macro["spx"].dropna(), macro["dxy"].dropna()
    gold, oil = macro["gold"].dropna(), macro["oil"].dropna().clip(lower=1.0)  # oil printed negative in Apr 2020
    flags = pd.DataFrame(
        {
            "spx_weak": spx < sma(spx, cfg["spx_sma"]),
            "dxy_surge": dxy.pct_change(cfg["dxy_lookback"]) > cfg["dxy_surge_pct"],
            "commodity_stress": (gold.pct_change(cfg["stress_lookback"]) > cfg["gold_spike_pct"])
            & (oil.pct_change(cfg["stress_lookback"]) > cfg["oil_spike_pct"]),
        }
    )
    flags = flags.fillna(False).reindex(index, method="ffill").fillna(False).astype(bool)
    flags["risk_off"] = flags.any(axis=1)
    return flags


def build_features(btc: pd.DataFrame, macro: pd.DataFrame, rules: dict, ext: pd.DataFrame | None = None) -> pd.DataFrame:
    reg, st = rules["regime"], rules["setup"]
    f = btc[["open", "high", "low", "close"]].copy()
    close = f["close"]
    f["ema_pb"] = ema(close, st["ema_pullback"])
    f["ema_fast"] = ema(close, reg["ema_fast"])
    f["ema_slow"] = ema(close, reg["ema_slow"])
    f["rsi"] = rsi(close, st["rsi_period"])
    f["atr"] = atr(f, st["atr_period"])

    lb = rules["exit"].get("donchian_lookback", 20)
    f["dc_mid"] = (close.rolling(lb).max() + close.rolling(lb).min()) / 2

    f["monthly_up"] = monthly_uptrend(close, reg["monthly_sma"])
    ens = reg.get("ensemble")
    if ens:  # share of Donchian lookbacks whose channel midpoint the close sits above
        votes = [close > (close.rolling(n).max() + close.rolling(n).min()) / 2 for n in ens["lookbacks"]]
        f["ens_share"] = sum(v.astype(float) for v in votes) / len(votes)
        f["daily_up"] = f["ens_share"] >= ens["min_share"]
    else:
        f["daily_up"] = (close > f["ema_slow"]) & (f["ema_fast"] > f["ema_slow"])
    f["trend_ok"] = f["monthly_up"] & f["daily_up"]
    f = f.join(macro_flags(macro, reg["macro"], f.index))
    f["regime_ok"] = f["trend_ok"] & ~f["risk_off"]

    f["pullback"] = (
        (close <= f["ema_pb"] * (1 + st["pullback_tolerance"]))
        & (close > f["ema_fast"])
        & (f["rsi"] < st["rsi_max"])
    )
    f["breakout"] = close >= close.rolling(st["breakout_days"]).max()
    f["setup"] = f["regime_ok"] & f["pullback"]
    f["signal"] = f["regime_ok"] & (f["breakout"] if rules["strategy"] == "trend" else f["pullback"])
    f["signal"] &= entry_filters(f, rules, ext)
    return f.dropna(subset=["ema_slow", "rsi", "atr"])


def entry_filters(f: pd.DataFrame, rules: dict, ext: pd.DataFrame | None) -> pd.Series:
    """Optional sentiment/on-chain vetoes on new entries; True everywhere when none are configured."""
    flt = rules.get("filters") or {}
    ok = pd.Series(True, index=f.index)
    if not any(v is not None for v in flt.values()):
        return ok
    if ext is None:
        raise ValueError("entry filters need external data: pass ext=load_external()")
    ext = ext.reindex(f.index).ffill(limit=3)  # a value dated D is published by D's close; tolerate short gaps
    f["fng"], f["mvrv"] = ext["fng"], ext["mvrv"]
    if flt.get("fng_block_at") is not None:
        ok &= ~(f["fng"] >= flt["fng_block_at"])
    if flt.get("fng_entry_max") is not None:
        ok &= f["fng"] <= flt["fng_entry_max"]
    if flt.get("mvrv_block_at") is not None:
        ok &= ~(f["mvrv"] >= flt["mvrv_block_at"])
    return ok
