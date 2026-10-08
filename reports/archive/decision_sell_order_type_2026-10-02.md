# Decision record: sell-order type on the live card (2026-10-02)

**Decision:** the card now tells you to place the protective sell as a **market stop** (Binance order type `STOP_LOSS`, shown in the app as
"Stop Market") instead of a stop-limit. If your Binance screen does not offer a market stop for BTC/USDT spot, the card prints the old
stop-limit prices as a fallback (trigger and a limit 0.5% below).

**Who decided:** you asked me to choose ("you can choose it yourself"). I chose on your stated priority, **protecting the capital**, and on
consistency with the backtest. I did **not** choose it to increase profit, and I cannot promise it does; the effect on profit is small and
not measurable from history.

## Why

- A stop-limit sell can fail to execute. The hourly check on the 48 historical stop-outs (`audit_2026-10-02.md`): inside the first hour price
  traded through the stop, the hour's low was a median 0.49% below it; in 23 of 48 cases price fell more than the 0.5% limit band within
  that single hour, and in 2 the hour closed below the limit price. In those cases a stop-limit could sit unfilled while price keeps falling.
- A market stop always exits. On an order of about $50 the slippage cost is small, and the backtest already assumes market-like exits
  (0.1% stop slippage in the base case, 0.5% in the harsh case). So a market stop matches the modelled behaviour better than a stop-limit does.
- The audit showed the edge is very sensitive to stop fills: if stops fill 1.5% worse than planned, the edge-test return falls from +57% to +14%.
  Avoiding unfilled stops matters more than saving a few hundredths of a percent.

## What did NOT change

The stop trigger levels, the trailing rule, the entry plan, the signal, the risk sizing, the circuit breakers and every file hashed in the
freeze records. Only the wording of how to place the protective order changed (`run.py`, `dashboard.py`, `watch.py`, `review.py`). The change
was made on 2026-10-02 before any paper trade existed, so forward results are not affected in kind.

## Caveats

- A market stop can fill below the trigger in a fast drop (that is the slippage the backtest assumes). It gives certainty of exit, not of price.
- I cannot see your Binance app. Check that a "Stop Market" option exists for BTC/USDT spot; otherwise use the fallback printed on the card.
- If you disagree, reverting is a text change in `spot_trd/run.py` (`stop_limit`) plus the dashboard and alert strings; the trigger levels never changed.
