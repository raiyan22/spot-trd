import pandas as pd

HORIZONS = (5, 10, 20)
SIGNATURE = ["monthly_up", "daily_up", "risk_off", "pullback"]


def forward_returns(close: pd.Series, horizons=HORIZONS) -> pd.DataFrame:
    return pd.DataFrame({f"fwd_{h}d": close.shift(-h) / close - 1 for h in horizons})


def analog_stats(fwd: pd.DataFrame, mask: pd.Series) -> pd.DataFrame:
    """Distribution of forward returns on the days selected by mask."""
    sub = fwd[mask]
    rows = {}
    for col in fwd.columns:
        s = sub[col].dropna()
        rows[col.removeprefix("fwd_")] = {
            "days": len(s),
            "mean": s.mean(),
            "median": s.median(),
            "pct_up": (s > 0).mean(),
            "worst_10pct": s.quantile(0.10),
        }
    return pd.DataFrame(rows).T


def regime_table(feat: pd.DataFrame) -> dict[str, pd.DataFrame]:
    fwd = forward_returns(feat["close"])
    groups = {
        "All days": pd.Series(True, index=feat.index),
        "Regime OK (all gates pass)": feat["regime_ok"],
        "Setup days (regime OK + pullback)": feat["setup"],
        "Regime blocked": ~feat["regime_ok"],
        "Macro risk-off": feat["risk_off"],
    }
    return {name: analog_stats(fwd, mask) for name, mask in groups.items()}


def current_analogs(feat: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    """Historical days whose regime signature matches the latest day."""
    last = feat.iloc[-1]
    sig = {k: bool(last[k]) for k in SIGNATURE}
    mask = pd.Series(True, index=feat.index)
    for k, v in sig.items():
        mask &= feat[k] == v
    mask.iloc[-1] = False
    return sig, analog_stats(forward_returns(feat["close"]), mask)
