# Amendment 1 to the intraday pre-registration

Written 2026-10-02 **after** the first run. The original pre-registration (`intraday_preregistration_2026-10-02.md`) is unchanged
and still hashed; the first run's report is preserved as `intraday_2026-10-02_run1_as_first_produced.md`.

## What happened

Section 6, check 3 of the pre-registration said a deliberately leaked variant (acting on a candle's signal at that same candle's
open) "must score visibly better than the correct pipeline". On the first run it did for A (-0.166% to +0.734% net per trade) and B
(-0.253% to +0.269%), but **not for C** (-0.353% to -1.782%). The check as written therefore failed.

## Why the check was ill-posed for C

C buys after a candle that closed below its lower Bollinger band. Buying that same candle at its *open* means buying before the drop
that created the signal, which is a worse price, not a better one. A leak in the timing does not have to improve every strategy; for
a mean-reversion entry it can hurt. So a "leaked version looks better" test cannot prove the test has power for C. This is a flaw in
my check design, not evidence of look-ahead in the pipeline.

## What I did not know when I wrote the original, and what I saw before writing this

I saw, on the failed verification line, the three mean net returns per trade (all negative), and then the full first-run result
tables (all three strategies lose after costs, none passes N2 or N3). So this amendment is not blind to the outcome. It is limited to
the verification method and **does not change any acceptance gate, threshold, cost, strategy rule or label**.

## Supplementary check added (replaces the leak-direction requirement; the original line is still printed)

**Mutation test of the perturbation check.** Build a deliberately look-ahead version of each strategy (it additionally requires that the
close 24 candles later is above the signal candle's close). Run the same perturbation test used for the real strategies. The harness has
power only if it **detects** the leak (trades exiting by a cut date differ after the future is replaced) in at least 3 of the 4 cut
dates, for each of A, B and C. The real strategies must still pass the perturbation test.

All-clear rule for the study: the perturbation test passes for the real A, B and C, and the mutation test shows the harness can detect
a leak for A, B and C. The original leak-direction line is reported as a non-gating observation.

## Why the verdict does not depend on this

Look-ahead errors can only make a backtest look better than reality. Every strategy here already loses money after costs, so an
undetected leak could not be hiding a profitable strategy; at worst it hides that the true result is even worse.

## Revision to the mutation test (same day)

The first implementation of the mutation test used the same 4 randomly placed cut dates as the real perturbation test. It detected the
deliberate leak on **0 of 4 cuts for A, B and C**, so the harness had no power as built: a 24-candle look-ahead rarely overlaps a trade
that exits before a random cut. That report was overwritten by the rerun; the numbers are recorded here instead. The test was changed so
the cut dates are placed where the leak can matter: **8 cuts per strategy, each at the midnight after a day on which the look-ahead
version entered a trade (evenly spaced across history)**. The pass rule is detection on at least 3 of 8 cuts (a flipped trade is
expected about half the time, since the perturbed future is random). The real strategies' perturbation test is unchanged (4 cuts).
