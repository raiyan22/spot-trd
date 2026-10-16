"""Live BTC chart: daily structure with the strategy's levels, plus recent 4H candles and the live price."""
import argparse

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from spot_trd.clock import local
from spot_trd.config import REPORTS_DIR, load_rules
from spot_trd.data import _exchange, load_data, retry
from spot_trd.regime import build_features

UP, DOWN = "#1a9e77", "#d95f5f"


def live_snapshot(symbol: str) -> tuple[dict, pd.DataFrame]:
    ex = _exchange()
    ticker = retry(lambda: ex.fetch_ticker(symbol))
    rows = retry(lambda: ex.fetch_ohlcv(symbol, "4h", limit=60))
    h4 = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    h4.index = pd.to_datetime(h4.pop("ts"), unit="ms")
    return ticker, h4


def candles(ax, df: pd.DataFrame, width: float) -> None:
    for ts, r in df.iterrows():
        color = UP if r["close"] >= r["open"] else DOWN
        ax.vlines(ts, r["low"], r["high"], color=color, linewidth=0.8)
        ax.bar(ts, max(abs(r["close"] - r["open"]), r["close"] * 0.0005), width,
               bottom=min(r["open"], r["close"]), color=color)


def render(feat: pd.DataFrame, ticker: dict, h4: pd.DataFrame, days: int = 150) -> str:
    feat = feat.iloc[-days:]
    live, when = ticker["last"], pd.Timestamp(ticker["timestamp"], unit="ms")
    last = feat.iloc[-1]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 9), height_ratios=[3, 2])
    for d in feat.index[feat["regime_ok"]]:
        ax1.axvspan(d - pd.Timedelta(hours=12), d + pd.Timedelta(hours=12), color=UP, alpha=0.07, linewidth=0)
    candles(ax1, feat, 0.7)
    for col, label, color in (("ema_pb", "EMA20", "#e6a817"), ("ema_fast", "EMA50", "#3b7dd8"), ("ema_slow", "EMA200", "#7a4fc9")):
        ax1.plot(feat.index, feat[col], label=label, color=color, linewidth=1.3)
    ax1.axhline(live, color="black", linestyle="--", linewidth=0.9, label=f"live {live:,.0f}")
    entry_zone = (last["close"] - 0.75 * last["atr"], last["close"] - 0.25 * last["atr"])
    ax1.axhspan(*entry_zone, color="#e6a817", alpha=0.12,
                label=f"ladder if a setup forms ({entry_zone[0]:,.0f}-{entry_zone[1]:,.0f})")
    ax1.scatter(feat.index[feat["signal"]], feat["low"][feat["signal"]] * 0.985, marker="^", color=UP, s=40,
                label="pullback setup", zorder=5)
    gate = "PASS" if last["regime_ok"] else "BLOCKED"
    ax1.set_title(f"BTC/USDT daily, last {days} days | regime gate {gate} (green shading = gate passed) | "
                  f"RSI {last['rsi']:.0f} | ATR {last['atr'] / last['close']:.1%}", fontsize=11)
    ax1.legend(loc="upper left", fontsize=8, ncol=3)
    ax1.grid(alpha=0.2)

    candles(ax2, h4, 0.12)
    ax2.axhline(live, color="black", linestyle="--", linewidth=0.9)
    ax2.axhline(last["ema_pb"], color="#e6a817", linewidth=1, label=f"daily EMA20 {last['ema_pb']:,.0f}")
    ax2.set_title(f"4H candles, last 10 days | live {live:,.2f} at {local(when)} "
                  f"(24h {ticker['percentage']:+.2f}%)", fontsize=11)
    ax2.legend(loc="upper left", fontsize=8)
    ax2.grid(alpha=0.2)

    fig.tight_layout()
    REPORTS_DIR.mkdir(exist_ok=True)
    path = REPORTS_DIR / f"chart_{when:%Y-%m-%d_%H%M}.png"
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return str(path)


def main() -> None:
    ap = argparse.ArgumentParser(description="Render the live BTC chart with the strategy's levels.")
    ap.add_argument("--days", type=int, default=150)
    days = ap.parse_args().days
    rules = load_rules()
    btc, macro = load_data(refresh=True)
    feat = build_features(btc, macro, rules)
    ticker, h4 = live_snapshot(rules["market"]["symbol"])
    print(f"Saved chart to {render(feat, ticker, h4, days)}")


if __name__ == "__main__":
    main()
