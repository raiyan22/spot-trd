# Execution comparison for frozen v2 signals (2026-10-02)

Pre-registration: `limit_entry_preregistration_2026-10-02.md` (frozen 2026-10-02T09:21:32+00:00); frozen files unchanged: **YES**. Analysis only; v2 is untouched. **A manual limit buy before a v2 card issues a plan changes the signal and is not evaluated; the default stays: no manual limit buy, wait for the frozen v2 signal.** Large account (100,000 USDT at 2% risk) so the minimum order does not distort; 2018-03-04 to 2026-10-01.

Plans issued: M0 62, M1 54, M2 82. Every method reads the same signal column from the frozen feature code; the counts differ only because a method that is already in a position, or that filled sooner or later, is flat on different days.

## 1. Results, base fills

| Method | Plans | Fill rate | Trades | Win rate | Mean R per filled trade | Mean R per signal (non-fill = 0) | Entry vs next open (price improvement) | Fees ($) | Total return | Max DD | Calmar |
|---|---|---|---|---|---|---|---|---|---|---|---|
| M0 current v2 ladder (2 limits) | 62 | 81% | 50 | 42% | +0.650 | +0.524 | +1.6% | 3,983 | +57.1% | -12.3% | 0.44 |
| M1 market at next open | 54 | 100% | 54 | 44% | +0.370 | +0.370 | -0.2% | 3,812 | +44.8% | -12.2% | 0.36 |
| M2 one limit at close - 0.5 ATR | 82 | 49% | 40 | 38% | +0.629 | +0.307 | +2.2% | 4,212 | +57.8% | -16.7% | 0.33 |

Harsh fills:

| Method | Plans | Fill rate | Trades | Mean R per filled trade | Mean R per signal | Total return | Max DD | Calmar |
|---|---|---|---|---|---|---|---|---|
| M0 current v2 ladder (2 limits) | 61 | 80% | 49 | +0.565 | +0.454 | +46.1% | -12.2% | 0.37 |
| M1 market at next open | 52 | 100% | 52 | +0.186 | +0.186 | +18.9% | -15.8% | 0.13 |
| M2 one limit at close - 0.5 ATR | 81 | 47% | 38 | +0.547 | +0.257 | +45.6% | -15.9% | 0.28 |

## 2. Opportunity cost of missed trades

| Method | Plans that never filled | Share of plans | Of those, signals a market entry also traded | Their mean R under market entry | Their total R |
|---|---|---|---|---|---|
| M0 current v2 ladder (2 limits) | 12 | 19% | 11 | +0.82R | +9.0R |
| M2 one limit at close - 0.5 ATR | 42 | 51% | 24 | +0.36R | +8.6R |

The R a missed plan would have earned is approximated by the market-entry run's trade for the same signal date; account states differ between runs, so treat it as indicative.

## 3. The $300 account (v2's risk schedule), base fills

| Method | Final capital | Profit per year | Trades | Max DD | Fees per year ($) |
|---|---|---|---|---|---|
| M0 current v2 ladder (2 limits) | 376.28 | $+8.89 | 51 | -6.2% | 0.62 |
| M1 market at next open | 370.02 | $+8.16 | 56 | -5.7% | 0.62 |
| M2 one limit at close - 0.5 ATR | 379.53 | $+9.27 | 41 | -9.0% | 0.64 |

## 4. Pre-registered test (alternatives vs M0, large account)

| Test | M1 market at next open | M2 one limit at close - 0.5 ATR |
|---|---|---|
| E1 gain >= 0.10R per signal and bootstrap lower bound > 0 | **FAIL** -0.154R, lower bound -0.311 | **FAIL** -0.218R, lower bound -0.534 |
| E2 Calmar >= M0 (base and harsh) | **FAIL** 0.36 vs 0.44; harsh 0.13 vs 0.37 | **FAIL** 0.33 vs 0.44; harsh 0.28 vs 0.37 |
| E3 max DD no more than 2 points worse | PASS -12.2% vs -12.3% | **FAIL** -16.7% vs -12.3% |
| E4 difference not negative in either half | **FAIL** -0.260 / -0.075 | **FAIL** +0.002 / -0.303 |
| E5 fill rate >= 70% | PASS 100% | **FAIL** 49% |
| **Outcome** | **NO CHANGE: keep M0** | **NO CHANGE: keep M0** |

## 5. Answer

- **Default: no manual limit buy. Wait for the frozen v2 signal.** When a card says BUY, place the plan's own two limit orders; that already is a limit-entry method.
- No alternative passed the pre-registered tests, so there is nothing to carry forward and no change to propose.