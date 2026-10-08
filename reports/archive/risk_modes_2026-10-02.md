# Higher-risk v2: can it reach +16.7% in 3-6 months? (2026-10-02)

Pre-registration: `risk_modes_preregistration_2026-10-02.md` (frozen 2026-10-02T08:27:24+00:00); frozen files unchanged: **YES**. $300 start, target $350, v2 rules untouched, circuit breakers on. History 2018-03-04 to 2026-10-01.

## 1. Arithmetic first

- v2's observed trade rate is 5.8 per year, so about 1.5 trades in 3 months and 2.9 in 6 months. It is also idle: in the 6-month windows below, the share with **zero trades** is reported per multiple.
- Average result per trade: +0.65R (base), +0.57R (harsh); median trade -0.35R; win rate 42%; spread of trade results (SD) 2.45R.
- **3 months:** expected total about +0.94R. For the *expected* return to equal +16.7%, risk per trade would have to be about **18% of capital** (harsh fills: 20%). That is the average case; the typical case is worse because the median trade loses.
- **6 months:** expected total about +1.89R. For the *expected* return to equal +16.7%, risk per trade would have to be about **9% of capital** (harsh fills: 10%). That is the average case; the typical case is worse because the median trade loses.
- **Spot-only ceiling.** With no leverage, a fully invested position can lose at most its stop distance. On v2's 220 historical signal days the standard ladder's stop distance is a median 5.0% (10th-90th percentile 3.3% to 9.1%), so risk per trade can never exceed roughly that, even going all-in on every trade.
- Required annualised pace: +16.7% in 6 months is about 36% a year; in 3 months about 85% a year. v2's historical rate at 2% risk is 5.4% a year (edge test).

## 2. Rolling historical windows

v2 restarted from $300 every 7 days. Windows overlap heavily: the history holds only about 17 independent 6-month windows and 34 independent 3-month windows, so read these as a handful of market episodes, not hundreds of observations.

### 3 months (base fills; harsh fills in the last column)

| Risk per trade | Windows | P(end >= +16.7%) | P(touches $350) | P(end < start) | P(<= -10% / -20%) | Median end | 5th pct / worst | Max DD median / worst-5% | P(DD >= 20%) | No trades | Harsh: reach / loss |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x (1%) | 435 | 0% | 0% | 37% | 0% / 0% | +0.0% | -1.9% / -2.9% | -0.8% / -2.5% | 0% | 39% | 0% / 39% |
| 2x (2%) | 435 | 0% | 5% | 38% | 0% / 0% | +0.0% | -3.8% / -5.8% | -1.6% / -4.9% | 0% | 39% | 0% / 39% |
| 3x (3%) | 435 | 7% | 9% | 38% | 0% / 0% | +0.0% | -5.8% / -8.5% | -2.4% / -7.4% | 0% | 39% | 6% / 39% |
| 5x (5%) | 435 | 12% | 14% | 38% | 0% / 0% | +0.0% | -8.2% / -10.6% | -3.2% / -9.8% | 0% | 39% | 11% / 39% |

### 6 months (base fills; harsh fills in the last column)

| Risk per trade | Windows | P(end >= +16.7%) | P(touches $350) | P(end < start) | P(<= -10% / -20%) | Median end | 5th pct / worst | Max DD median / worst-5% | P(DD >= 20%) | No trades | Harsh: reach / loss |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x (1%) | 422 | 0% | 0% | 41% | 0% / 0% | +0.0% | -2.5% / -4.1% | -1.6% / -3.2% | 0% | 27% | 0% / 42% |
| 2x (2%) | 422 | 2% | 16% | 41% | 0% / 0% | +0.0% | -5.0% / -6.7% | -3.1% / -6.3% | 0% | 27% | 2% / 42% |
| 3x (3%) | 422 | 19% | 23% | 42% | 4% / 0% | +0.0% | -8.3% / -12.0% | -4.7% / -10.1% | 0% | 27% | 12% / 43% |
| 5x (5%) | 422 | 24% | 28% | 42% | 10% / 0% | +0.0% | -10.6% / -15.1% | -7.3% / -14.1% | 0% | 27% | 24% / 44% |

## 3. Monte Carlo from observed trade results

Resampling the 50 observed R multiples (edge test, base fills) at 5.8 trades a year. No circuit breaker and no cash cap, so it slightly overstates both gains and losses at high multiples. MC 'worst' is the 0.5th percentile.

| Horizon | Risk per trade | P(end >= +16.7%) | P(end < start) | P(<= -10%) | Median end | 5th pct / worst | Max DD worst-5% | P(DD >= 20%) | No trades |
|---|---|---|---|---|---|---|---|---|---|
| 3 months | 1x (1%) | 0% | 39% | 0% | +0.0% | -1.8% / -2.9% | -2.0% | 0% | 23% |
| 3 months | 2x (2%) | 5% | 40% | 0% | +0.0% | -3.5% / -5.8% | -4.0% | 0% | 23% |
| 3 months | 3x (3%) | 10% | 40% | 0% | +0.0% | -5.3% / -8.6% | -5.9% | 0% | 23% |
| 3 months | 5x (5%) | 15% | 40% | 2% | +0.0% | -8.7% / -14.1% | -9.7% | 0% | 23% |
| 6 months | 1x (1%) | 1% | 42% | 0% | +0.2% | -2.4% / -4.0% | -2.8% | 0% | 5% |
| 6 months | 2x (2%) | 9% | 43% | 0% | +0.4% | -4.8% / -7.8% | -5.5% | 0% | 5% |
| 6 months | 3x (3%) | 18% | 43% | 1% | +0.5% | -7.1% / -11.5% | -8.2% | 0% | 5% |
| 6 months | 5x (5%) | 26% | 43% | 8% | +0.8% | -11.7% / -18.6% | -13.4% | 0% | 5% |

## 4. Pre-registered criteria (6-month horizon)

R1 reach >= 50%; R2 loss <= 20% (also harsh); R3 P(DD >= 20%) <= 10% (also harsh); R4 5th percentile >= -15% and worst >= -25% (also harsh); R5 history and Monte Carlo agree on R1-R4; R6 risk per trade <= 3%.

| Risk per trade | R1 reach | R2 loss | R3 drawdown | R4 tail | R5 history = MC | R6 bounded | Result |
|---|---|---|---|---|---|---|---|
| 1x (1%) | **FAIL** | **FAIL** | PASS | PASS | PASS | PASS | **REJECTED** |
| 2x (2%) | **FAIL** | **FAIL** | PASS | PASS | PASS | PASS | **REJECTED** |
| 3x (3%) | **FAIL** | **FAIL** | PASS | PASS | PASS | PASS | **REJECTED** |
| 5x (5%) | **FAIL** | **FAIL** | PASS | PASS | PASS | **FAIL** | **REJECTED** |

## 5. How long would +16.7% plausibly take? (descriptive only; not used to pick a multiple)

| Risk per trade | 6 months | 12 months | 24 months |
|---|---|---|---|
| 1x (1%) | 0% reach, 41% loss, median +0.0% | 0% reach, 36% loss, median +2.6% | 5% reach, 16% loss, median +7.1% |
| 2x (2%) | 2% reach, 41% loss, median +0.0% | 14% reach, 36% loss, median +5.2% | 44% reach, 16% loss, median +14.3% |
| 3x (3%) | 19% reach, 42% loss, median +0.0% | 21% reach, 41% loss, median +4.2% | 36% reach, 37% loss, median +4.7% |
| 5x (5%) | 24% reach, 42% loss, median +0.0% | 39% reach, 37% loss, median +8.0% | 60% reach, 18% loss, median +28.2% |

## 6. Could a paper test validate a higher-risk mode?

To tell an average of +0.65R per trade (SD 2.45R) from zero with 80% power you need about **112 trades**. At 5.8 trades a year that is about **19 years** of forward paper trading. A year of paper results (about 6 trades) cannot confirm expectancy; it can only reveal gross breakage. Raising risk does not change this: expectancy in R is the same at every multiple, while the dollar swings grow.

## 7. Verdict

- **Arithmetic rejects the target.** Making the expected 6-month return equal +16.7% needs about 9% risk per trade. A spot position can lose at most its stop distance: a median 5.0% of the position, 3.3% at the 10th percentile. Even investing everything in every trade could not reach the required risk.
- **No predetermined multiple meets R1-R6. The +16.7% in 3-6 months target is rejected for v2.**
- For scale: at 5x the chance of ending 6 months at or above target was 24% while the chance of ending below the start was 42%; at 2x the figures were 2% and 41%.

## 8. Reading notes

- **R1 alone rejects every multiple** (best case 24% reach against the 50% bar). R2 as written (any loss at all in at most 20% of windows) is strict: v2 ends a 6-month window slightly below its start in about 40% of windows even at 1x, because it takes small losses between rare winners. How big the losses are matters more: see the 'P(<= -10% / -20%)' and 5th-percentile columns, where 1x to 3x stay small and 5x reaches about -11% at the 5th percentile and -15% at the worst window.
- The 12 and 24 month rows are not monotonic in risk (for example 3x reaches the target less often than 2x at 24 months). Two reasons: v2's circuit breaker (5% below peak pauses new entries for 30 days) fires far more often as risk rises, and there are only about four independent 24-month windows in the history. Treat those rows as episodes, not statistics.
- Reaching $350 at some point inside a window (the 'touches' column) is not the same as ending there: v2 has no profit target, so gains are given back if the trade is not closed at the right moment.