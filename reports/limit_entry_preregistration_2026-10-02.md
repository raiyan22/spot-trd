# Execution comparison for frozen v2 signals: pre-registration

Written 2026-10-02 **before any execution-variant result existed.** Hashed in `reports/limit_entry_freeze_2026-10-02.json` with the live
strategy files. Later changes go in a dated amendment at the bottom.

## 0. Scope and stance

- The project is in **forward observation mode**. This is an **analysis**, not a new strategy phase. v2, its signal and its risk rules
  stay frozen and live in paper mode exactly as they are.
- **A manual limit buy placed before a v2 card issues a plan is a different strategy**, because it enters without the v2 signal. It cannot
  be evaluated as "preserving the signal" and is **not allowed**. The default stays: *no manual limit buy; wait for the frozen v2 signal.*
  When a v2 card does say BUY, the plan it prints is already a pair of limit buys, and those exact orders are what to place.
- What can be compared is how the **same v2 signals** are executed. Signals are identical across methods by construction (the
  signal columns come from the frozen feature code); nothing below may create or remove a signal.
- Even a favourable result here changes nothing live. A promising variant would need your explicit approval and then its own,
  stricter pre-registration (exact rules, minimum improvement, drawdown constraint, out-of-sample plan) frozen before it is tested,
  and forward paper evidence before any use.

## 1. The three methods (fixed; no parameter is searched)

All three use the same signal bar, the same ATR, the same initial stop level (the lowest ladder price minus 1 ATR, i.e. close
- 1.75 ATR), the same 2 ATR trailing stop, regime exit, circuit breakers, risk schedule and sizing rule (worst-case loss at the stop
within the risk budget, Binance minimum order enforced), and the same fees.

- **M0, current v2 execution (control).** Two resting limit buys at signal close - 0.25 ATR and close - 0.75 ATR, equal notional, valid
  for the next 2 daily bars, unfilled orders cancelled at expiry. Non-fill of a tranche means a smaller position; of both, no trade.
- **M1, market at the next open.** One market buy at the open of the bar after the signal, with adverse slippage (0.1% base, 0.3% harsh).
  Sized for the same risk budget against the same stop, so the position is smaller than M0's because the entry is higher.
- **M2, single limit.** One resting limit buy at signal close - 0.5 ATR (the average of M0's two prices), valid 2 daily bars, cancelled at
  expiry. Non-fill means no trade and **no re-chase**. Maximum distance from the signal price is therefore 0.5 ATR (about 1.4% at
  a typical ATR of 2.7%).

Fills: a resting limit fills only if the daily low trades through it by 0.05% (base) or 0.15% (harsh), or the bar opens at or below it.
Fee 0.1% per side. Stops and exits as in the audit's base and harsh fill models.

## 2. Metrics

Per method: plans issued, fill rate (plans that produced a position), trades, win rate, mean R **per filled trade**, mean R **per signal**
(non-fills count as zero: this is what the opportunity cost of missing a trade does to expectancy), average entry versus the next
open (slippage saved or price improvement), fees, total return, maximum drawdown and Calmar. The R that each missed M0/M2 plan would
have earned had it been entered at the next open (market entry, same exits) is reported as the opportunity cost of non-fills (an
approximation, since account states differ). Evaluated on the large account (100,000 USDT at 2% risk) so the minimum order does not
distort, and at $300. Base and harsh fills. Full period, plus the halves before and after 2023-01-01 (2023-onward is
contaminated for v2 itself; it is a consistency check).

## 3. What would count as promising

An alternative (M1 or M2) is **worth a separate pre-registration** only if ALL hold against M0 on the large account with base fills:

- **E1:** mean R per signal is higher by at least **0.10R**, and the lower bound of a one-sided 97.5% bootstrap interval for the
  difference (plans resampled in monthly blocks; 97.5% because two alternatives are compared) is above zero.
- **E2:** Calmar is at least M0's under base fills **and** under harsh fills.
- **E3:** maximum drawdown is no more than 2 percentage points worse than M0's.
- **E4:** the mean-R-per-signal difference is not negative in either half.
- **E5:** fill rate of at least 70% (M2 only; M1 is always 100% by definition).

If none qualifies, M0 stays and the report says that plainly. Slippage saved is not by itself a reason: it must survive the opportunity
cost of missed trades.

## 4. Verification

The signal series are identical across methods (checked). Entry price uses only the signal bar's close and ATR, and the next bars'
prices only for fills. Default execution (M0) must reproduce the published v2 results exactly (regression test).
