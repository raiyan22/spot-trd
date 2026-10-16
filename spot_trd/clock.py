"""Times shown to you are in your local time (config/watch.yaml `display_utc_offset_hours`, default UTC+6).

Everything stored and decided stays in UTC (journal, logs, the 00:00 UTC daily close); this only formats what you read.
"""
from functools import lru_cache

import pandas as pd


@lru_cache(maxsize=1)
def offset_hours() -> float:
    try:
        from spot_trd.config import load_watch
        return float(load_watch().get("display_utc_offset_hours", 6))
    except Exception:
        return 6.0


def label() -> str:
    h = offset_hours()
    return "UTC" if h == 0 else f"UTC{h:+g}"


def to_local(ts) -> pd.Timestamp:
    return pd.Timestamp(ts) + pd.Timedelta(hours=offset_hours())


def from_local(ts) -> pd.Timestamp:
    """A time you typed in your local time, as naive UTC."""
    return pd.Timestamp(ts) - pd.Timedelta(hours=offset_hours())


def local(ts, fmt: str = "%Y-%m-%d %H:%M") -> str:
    """e.g. '2026-10-18 06:00 UTC+6' for 2026-10-18 00:00 UTC."""
    return f"{to_local(ts):{fmt}} {label()}"


def local_hm(ts) -> str:
    return local(ts, "%H:%M")


def daily_close() -> str:
    """The 00:00 UTC daily close in your time, e.g. '06:00 UTC+6'."""
    return local_hm(pd.Timestamp("2000-01-01"))
