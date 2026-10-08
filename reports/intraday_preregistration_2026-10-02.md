# Intraday BTC strategies: pre-registration

Written 2026-10-02 **before any intraday data was downloaded or any intraday result computed.** Hashed in
`reports/intraday_freeze_2026-10-02.json` with the frozen live-strategy files. Later changes go in a dated amendment at the
bottom; the original text stays.

## 0. Question and stance

Does a predefined, long-only, spot, intraday BTC/USDT strategy have **positive expectancy after realistic costs**?

- No trade is forced: a day with no setup is a flat day. Filters that skip trades are part of the definition, not tuning.
- Parameters are conventional textbook values written down now. **Nothing is searched, tuned or re-run with different values.**
- Three strategies, one per standard family (breakout, trend-pullback, mean reversion). Because three were tried, significance
  is corrected for three (section 5).
- The live paper strategy (v2) is not touched. This is research only; nothing here can go live without forward evidence.
- Prior, disclosed: round-trip cost of about 0.3% is large against typical intraday moves, and public intraday studies mostly
  find no edge after fees. The expected outcome is "no edge". The result decides, not the prior.
- The intraday data has never been examined in this project, so the whole history is out-of-sample *for these parameters*.
  Strategy B also uses v2's daily regime gate, which was designed on the full daily history (a mild contamination, disclosed).

## 1. Data and timing

Binance BTC/USDT 1-hour candles, 2017-08 onward, completed candles only. Candles are labelled by **open time, UTC**. Evaluation
period: 2018-03-04 to the last completed candle (the same start as the daily studies).

- A decision made from a candle is known at that candle's **close**; the order executes at the **next candle's open**. Nothing
  else may be used.
- Daily gates use the **previous completed UTC day only**.
- At most **one entry per UTC day**. All positions are flat by the open of the 23:00 candle (nothing is held overnight).
- Entries are allowed only when the next candle's open hour is between 01:00 and 20:00 UTC (so there is time to exit).
- Long only, one position at a time, spot, no leverage.

## 2. The three strategies

**A. Opening-range breakout.** Range = highest high and lowest low of the 00:00-03:00 candles. Signal: the first candle with open hour
04:00-19:00 whose close is above the range high. Skip the day if (range high - range low) / range high < 0.5%. Stop = range low.
No target. Exit at stop or the 23:00 open.

**B. Gated pullback-reclaim.** Gate: v2's daily `regime_ok` for the previous completed day. On 1h closes use EMA20 and EMA50 and ATR14.
Signal: at least one of the last 8 closes was below EMA20, the current close is above EMA20, EMA20 > EMA50, and the candle closed
above its open. Stop = lowest low of the last 8 candles minus 0.5 x ATR14. Exit at the stop, the next open after any close below
EMA50, or the 23:00 open. No target.

**C. Mean reversion.** Gate: previous completed day's close above its 200-day simple moving average. Bollinger bands (20, 2) and RSI14
on 1h closes. Signal: close below the lower band and RSI14 below 30. Target = the middle band (20-period mean) at signal time, as a
resting limit sell. Skip if (target - entry reference) / entry reference < 0.4%. Stop = entry reference - 1.5 x ATR14. Exit at
target, stop, or the 23:00 open.

(Entry reference = the signal candle's close.)

## 3. Costs and fills

| | Base | Harsh |
|---|---|---|
| Fee per side (no BNB discount) | 0.10% | 0.10% |
| Slippage on market entries and exits | 0.05% | 0.15% |
| Stop slippage (below the stop or the open, whichever is lower) | 0.10% | 0.30% |
| Limit target fills only if price trades through by | 0.05% | 0.15% |

Worst-case ordering inside a candle: a stop is assumed hit before a target, including on the entry candle. Round-trip cost in
the base case is about 0.3% before any stop slippage. Binance minimum order 5 USDT x 1.1, lot 0.00001 BTC; a trade that cannot
reach the minimum is skipped.

Sizing at $300: risk 1% of equity per trade over (stop distance + round-trip cost), capped at 98% of cash. Because intraday stops
are tight, positions often hit the cash cap, so the effective risk per trade is below 1%.

## 4. Metrics

Per strategy: trades, trades per year, share of days traded, win rate, mean gross and net return per trade, cost per trade,
expectancy in R (net return per trade divided by planned risk fraction: stop distance plus round-trip cost; position-independent),
median trade, profit factor, losing streak, time in market, fees and slippage in dollars, and for the $300 account: annualised
return, maximum drawdown (hourly equity), Sharpe (daily), profit per year. Calendar years and two halves (before and after 2022-07-01).

## 5. Acceptance criteria

All statistics use net-of-cost results. Significance is a one-sided block bootstrap (blocks = calendar weeks of exit date, 10,000
resamples) with **Bonferroni correction for three strategies**: the lower bound is taken at 98.33% one-sided.

- **N1 Sample:** at least 300 trades, else INSUFFICIENT.
- **N2 Significance:** the corrected lower bound of mean net R is above 0.
- **N3 Cost robustness:** mean net R is above 0 under harsh costs, and the break-even round-trip cost (the cost at which mean net
  return reaches zero) is at least 1.5x the base round-trip cost.
- **N4 Stability:** mean net R above 0 in both halves, and in at least 6 of the 9 calendar years (2018 and 2026 are partial).
- **N5 Beats drift:** mean net return per trade is above the 95th percentile of 200 random-entry runs with the same number of
  trades, entries at random eligible candles, a 1.5 x ATR14 stop and the 23:00 exit (this separates real signal from simply being
  long BTC for part of the day).
- **N6 Economics ($300, base fills):** annualised return at least 5% with maximum drawdown at most 15%, and still profitable under
  harsh costs.

**Labels.** NO EDGE: INSUFFICIENT, or fails N2 or N3. NOT ROBUST: passes N1-N3 but fails N4 or N5. WEAK: passes N1-N5 but fails N6.
WORTH FORWARD-TESTING: passes all. Even then, live use needs forward evidence first; a historical study cannot provide it.

## 6. Look-ahead verification (before results are read)

1. Indicators at candle t equal their value computed from candles up to t only.
2. Perturbation test: replace every candle after random cut dates with different prices; every trade that exits by the cut must be
   identical, for each strategy.
3. Leak detector: a deliberately leaked variant (acting on a candle's signal at that same candle's open) must score visibly better
   than the correct pipeline, proving the test has power.
4. Daily gates use the previous day only: shifting the gate one day earlier must not use a value that includes the current day.
5. No trade after the 20:00 open, none held through the 23:00 open, and no more than one entry per day.
