import os
import time

import ccxt
import pandas as pd
import yfinance as yf

from spot_trd.config import RAW_DIR

MACRO_TICKERS = {"spx": "^GSPC", "gold": "GC=F", "oil": "CL=F", "dxy": "DX-Y.NYB"}


def retry(fn, tries: int = 3, wait: float = 2.0):
    """Retry transient network failures with backoff; the last error propagates."""
    for attempt in range(tries):
        try:
            return fn()
        except Exception:
            if attempt == tries - 1:
                raise
            time.sleep(wait * 2 ** attempt)


def _exchange() -> ccxt.binance:
    ex = ccxt.binance({"enableRateLimit": True, "options": {"fetchMarkets": {"types": ["spot"]}}})
    if os.environ.get("SPOT_BINANCE_MARKET_DATA"):
        # Binance's public market-data mirror; api.binance.com refuses some cloud regions (HTTP 451), e.g. GitHub runners.
        ex.urls["api"]["public"] = "https://data-api.binance.vision/api/v3"
    return ex


def fetch_ohlcv(symbol: str = "BTC/USDT", timeframe: str = "1d", since: str = "2017-08-01") -> pd.DataFrame:
    ex = _exchange()
    since_ms = ex.parse8601(f"{since}T00:00:00Z")
    tf_ms = ex.parse_timeframe(timeframe) * 1000
    rows: list[list] = []
    while True:
        batch = retry(lambda: ex.fetch_ohlcv(symbol, timeframe, since=since_ms, limit=1000))
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < 1000:
            break
        since_ms = batch[-1][0] + tf_ms
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"]).drop_duplicates("ts")
    now_ms = int(time.time() * 1000)
    df = df[df["ts"] + tf_ms <= now_ms]  # drop the candle that is still forming
    df.index = pd.to_datetime(df["ts"], unit="ms")
    df.index.name = "date"
    return df.drop(columns="ts").astype(float)


def market_limits(symbol: str = "BTC/USDT") -> dict:
    ex = _exchange()
    retry(ex.load_markets)
    m = ex.market(symbol)
    return {
        "type": m["type"],
        "min_notional": m["limits"]["cost"]["min"],
        "qty_step": m["precision"]["amount"],
        "maker_fee": m.get("maker"),
        "taker_fee": m.get("taker"),
    }


def fetch_macro(start: str = "2016-06-01") -> pd.DataFrame:
    cols = {}
    for name, ticker in MACRO_TICKERS.items():
        hist = retry(lambda: yf.Ticker(ticker).history(start=start, auto_adjust=False))
        if hist.empty:
            raise RuntimeError(f"yfinance returned no data for {ticker}")
        s = hist["Close"]
        s.index = s.index.tz_localize(None).normalize()
        cols[name] = s
    df = pd.DataFrame(cols)
    df.index.name = "date"
    return df


def fetch_fng() -> pd.Series:
    """Crypto Fear & Greed Index (alternative.me), daily since Feb 2018. 0 = extreme fear, 100 = extreme greed."""
    import requests

    rows = retry(lambda: requests.get("https://api.alternative.me/fng/?limit=0&format=json", timeout=30).json())["data"]
    s = pd.Series({pd.to_datetime(int(r["timestamp"]), unit="s"): float(r["value"]) for r in rows}).sort_index()
    s.index.name = "date"
    return s.rename("fng")


def fetch_mvrv(start: str = "2017-01-01") -> pd.Series:
    """BTC market value / realized value from the Coin Metrics community API (free tier)."""
    import requests

    url = ("https://community-api.coinmetrics.io/v4/timeseries/asset-metrics?assets=btc&metrics=CapMVRVCur"
           f"&frequency=1d&start_time={start}&page_size=10000&paging_from=start")
    vals = {}
    while url:
        page = retry(lambda: requests.get(url, timeout=60).json())
        for r in page["data"]:
            vals[pd.Timestamp(r["time"]).tz_localize(None).normalize()] = float(r["CapMVRVCur"])
        url = page.get("next_page_url")
    s = pd.Series(vals).sort_index()
    s.index.name = "date"
    return s.rename("mvrv")


def load_external(refresh: bool = False) -> pd.DataFrame:
    """Sentiment and on-chain series used by optional filters (cached like the price data)."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / "external.parquet"
    if refresh or not path.exists():
        pd.concat([fetch_fng(), fetch_mvrv()], axis=1).to_parquet(path)
    return pd.read_parquet(path)


def load_data(refresh: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    btc_path, macro_path = RAW_DIR / "btc_1d.parquet", RAW_DIR / "macro.parquet"
    if refresh or not btc_path.exists():
        fetch_ohlcv().to_parquet(btc_path)
    if refresh or not macro_path.exists():
        fetch_macro().to_parquet(macro_path)
    return pd.read_parquet(btc_path), pd.read_parquet(macro_path)
