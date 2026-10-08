# Higher-risk v2: can it plausibly reach +16.7% ($300 to $350) in 3 to 6 months?

Written 2026-10-02 **before any result of this study existed.** Hashed in `reports/risk_modes_freeze_2026-10-02.json` together with
the frozen live-strategy files. Edits after results exist go in a dated amendment at the bottom.

## 0. Question and stance

Question: can frozen v2, with its per-trade risk raised by **predetermined** multiples, plausibly turn $300 into $350 (+16.66%)
within 3 or 6 months, and at what drawdown and probability of loss?

- The target is something to be **tested and, if the evidence says so, rejected**. The multiplier is not tuned to reach it.
- v2's rules, files and circuit breakers are untouched. Only the risk percentage is overridden, from outside the strategy.
- This is research on history. It is not a recommendation to trade at higher risk and it does not touch the paper strategy.

## 1. Predetermined multiples

Multiples of v2's 1% per-trade risk at $300: **1x (1%, the live setting), 2x (2%), 3x (3%), 5x (5%)**. Nothing else is tested. A
risk mode is "bounded" only if per-trade risk is **at most 3%** of capital (one stop-out loses at most $9 of $300). The 5x row is
included to show where the limit is, and fails that bound by definition.

## 2. Evidence (three independent views)

1. **Rolling historical windows.** v2 started fresh with $300 at every 7th day from 2018-03, run for 91, 182 (the gated horizons),
   and 365 and 730 days (informational only). Base fills, then harsh fills. Circuit breakers on. Windows overlap heavily; the number of
   non-overlapping windows is reported and the evidence is described by that smaller number.
2. **Monte Carlo** from the observed per-trade R multiples (edge test, base fills): Poisson number of trades at v2's observed rate,
   each trade returning R x risk% of equity, compounding. No circuit breaker, no cash cap, so it slightly overstates both gain and
   loss at high multiples (stated in the report).
3. **Arithmetic.** The per-trade risk that would make the *expected* 3 or 6 month return equal 16.66% (expected R per trade times
   expected trades in the window), and the spot-only ceiling on risk per trade: with no leverage, a fully invested position can lose
   at most its stop distance, so per-trade risk cannot exceed that distance (measured from historical v2 setups).

## 3. Acceptance criteria

A multiple counts as an **acceptable bounded higher-risk mode** only if ALL hold at the 6-month horizon with base fills, and R2-R5
also hold under harsh fills:

- **R1 Reach:** probability the window ends at or above +16.66% is at least 50%.
- **R2 Loss:** probability the window ends below its starting capital is at most 20%.
- **R3 Drawdown:** probability of a within-window drawdown of 20% or more is at most 10%.
- **R4 Tail:** the 5th-percentile window return is at least -15% and the worst window at least -25%.
- **R5 Not a fluke:** the historical windows and the Monte Carlo agree on pass/fail for R1-R4.
- **R6 Bounded:** per-trade risk at most 3%.

**If no multiple satisfies R1-R6, the +16.7% in 3 to 6 months target is rejected for v2.** The report also states whether the arithmetic
requirement exceeds the spot-only ceiling, which by itself rejects the target regardless of the rolling results.

The 3-month horizon is reported with the same statistics but is not a gate. The 12 and 24 month horizons are descriptive only: they
say how long the target would plausibly take, and are not used to pick a multiple.

## 4. Forward evidence note (to be answered in the report)

How many trades a paper test needs to tell v2's expectancy from zero, using the observed trade-to-trade spread, and how long that
takes at v2's trade rate. A mode that cannot be verified in a reasonable time cannot be promoted on forward evidence.

## 5. Compounding to a new base

Resetting the base to $350 after the target is hit changes nothing about expectancy or risk per trade: it only rescales dollars.
It is not a separate test.
