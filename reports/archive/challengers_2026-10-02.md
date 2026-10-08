# Challenger study results (2026-10-02)

Pre-registration: `challenger_preregistration_2026-10-02.md` (frozen 2026-10-02T08:10:15+00:00). Frozen files unchanged since freeze: **YES**. Period 2018-03-04 to 2026-10-01, BTC/USDT daily, same execution framework for every strategy. Gates are evaluated at $300; labels follow the pre-registered rules and are not rankings.

Matched exposure w* = 4.3% for the 200-day trend rule and 2.7% for buy-and-hold: the exposure at which each has the control's edge-test maximum drawdown (-12.3%). (Uses the full-sample drawdown, so it supports comparison only.)

## 1. Look-ahead verification (run before reading results)

- SMA identity: sma[t] equals the mean of closes t-199..t on 25 random dates: **PASS**.
- Perturbation test: replacing all bars after 5 cut dates with different random prices left every equity curve unchanged up to the cut for C1 100%, C1 w*, core and C3 25%: **PASS**.
- Leak detector: acting on a day's signal at that same day's open (a deliberate leak) turns 1,000 into 174,043, versus 7,442 for the correct next-open pipeline: **PASS (leak is visible)**.
- No rebalancing: BTC held is constant between every entry and exit on 33 round trips of C1 w*: **PASS**. Exposure is set once at entry from the account cash at that open.

## 2. Gates (pre-registered)

PASS/FAIL with the measured value. G1-G4 are hard gates; G5-G6 decide HOLD vs candidate. 4c (12 months of forward shadow results) cannot be met by a historical study and is required before any live use.

| Gate | C0 v2 control | C1 trend 100% | C1 trend w* | C3 core 10% + v2 90% | C3 core 25% + v2 75% | C3 core 50% + v2 50% |
|---|---|---|---|---|---|---|
| 1a halves > 0 | PASS +16.5% / +7.6% | PASS +114.8% / +246.4% | PASS +11.5% / +7.2% | PASS +19.2% / +56.3% | PASS +23.3% / +125.2% | PASS +29.9% / +230.6% |
| 1b harsh keeps 60% | PASS 81% | PASS 93% | PASS 97% | PASS 96% | PASS 98% | PASS 100% |
| 1c rolling 3y | PASS 87% positive, worst -1.3% | PASS 100% positive, worst +35.2% | PASS 100% positive, worst +0.5% | PASS 100% positive, worst +5.2% | PASS 100% positive, worst +11.2% | PASS 100% positive, worst +16.7% |
| 1d ex best 3 trades | PASS +3.67 $ | **FAIL** -106.55 $ | **FAIL** -5.24 $ | PASS +194.02 $ | PASS +479.64 $ | PASS +955.43 $ |
| 2a executable at $100 | PASS skipped 1% | PASS skipped 0% | **FAIL** skipped 100% | PASS skipped 11% | PASS skipped 25% | **FAIL** skipped 44% |
| 2b gap stress > 0 | PASS +11.8% | PASS +373.7% | PASS +17.0% | PASS +74.2% | PASS +167.8% | PASS +324.7% |
| 3a max DD <= 15% | PASS -6.2% / -6.6% | **FAIL** -64.7% / -66.0% | PASS -12.3% / -12.4% | **FAIL** -28.6% / -28.9% | **FAIL** -48.5% / -48.7% | **FAIL** -64.1% / -64.1% |
| 3b worst 12m >= -10% | PASS -6.2% / -6.5% | **FAIL** -64.7% / -66.0% | **FAIL** -12.3% / -12.4% | **FAIL** -28.3% / -28.6% | **FAIL** -48.0% / -48.3% | **FAIL** -63.6% / -63.6% |
| 3c BTC-down years >= -10% | PASS 2018 +0.0%, 2022 +0.0% | **FAIL** 2018 -35.1%, 2022 +0.0% | PASS 2018 -1.7%, 2022 +0.0% | **FAIL** 2018 -6.8%, 2022 -17.7% | **FAIL** 2018 -17.0%, 2022 -34.3% | **FAIL** 2018 -34.0%, 2022 -49.7% |
| 4a 2023+ CAGR > 0 | PASS +2.0% / +1.4% | PASS +39.3% / +36.9% | PASS +1.9% / +1.8% | PASS +12.7% / +12.4% | PASS +24.2% / +24.1% | PASS +37.6% / +37.5% |
| 4b no tuned parameters | PASS declared in advance | PASS declared in advance | PASS declared in advance | PASS declared in advance | PASS declared in advance | PASS declared in advance |
| 5a Calmar >= 1.25x control | **FAIL** 0.43 vs 0.43 | **FAIL** 0.41 vs 0.43 | **FAIL** 0.17 vs 0.43 | **FAIL** 0.26 vs 0.43 | **FAIL** 0.26 vs 0.43 | **FAIL** 0.29 vs 0.43 |
| 5b harsh Calmar >= control | PASS 0.33 vs 0.33 | PASS 0.37 vs 0.33 | **FAIL** 0.16 vs 0.33 | **FAIL** 0.25 vs 0.33 | **FAIL** 0.26 vs 0.33 | **FAIL** 0.29 vs 0.33 |
| 5c CAGR >= control | PASS +2.7% vs +2.7% | PASS +26.4% vs +2.7% | **FAIL** +2.1% vs +2.7% | PASS +7.5% vs +2.7% | PASS +12.7% vs +2.7% | PASS +18.6% vs +2.7% |
| 6b beats matched C1 by 10% | PASS 0.33 vs 0.15 | PASS n/a (is the baseline) | PASS n/a (is the baseline) | PASS 0.25 vs 0.21 | **FAIL** 0.26 vs 0.31 | **FAIL** 0.29 vs 0.37 |
| 6c beats core-only by 10% | PASS n/a | PASS n/a | PASS n/a | PASS 0.25 vs 0.19 | PASS 0.26 vs 0.23 | **FAIL** 0.29 vs 0.27 |
| **Outcome** | **HOLD** | **REJECT** | **REJECT** | **REJECT** | **REJECT** | **REJECT** |

## 3. Full metrics, $300 account, full period, base fills

| Metric | C0 v2 control | C1 trend 100% | C1 trend w* | C3 core 10% + v2 90% | C3 core 25% + v2 75% | C3 core 50% + v2 50% | BTC buy & hold 100% | BTC buy & hold w* |
|---|---|---|---|---|---|---|---|---|
| CAGR | +2.7% | +26.4% | +2.1% | +7.5% | +12.7% | +18.6% | +26.2% | +1.9% |
| Total return | +25.4% | +644.0% | +19.6% | +86.4% | +178.0% | +330.5% | +635.6% | +17.1% |
| Max drawdown | -6.2% | -64.7% | -12.3% | -28.6% | -48.5% | -64.1% | -76.6% | -12.2% |
| Sharpe | 0.78 | 0.76 | 0.49 | 0.56 | 0.58 | 0.63 | 0.69 | 0.37 |
| Calmar | 0.43 | 0.41 | 0.17 | 0.26 | 0.26 | 0.29 | 0.34 | 0.15 |
| Profit factor | 2.11 | 2.83 | 4.09 | 2.11 | 2.11 | 2.12 | n/a | n/a |
| Round trips per year | 5.9 | 3.8 | 3.8 | 5.9 | 5.9 | 5.9 | 0.0 | 0.0 |
| Time invested | 16% | 52% | 52% | 100% | 100% | 100% | 100% | 100% |
| Capital utilisation (BTC value / equity) | 2% | 52% | 4% | 24% | 44% | 65% | 100% | 8% |
| Fees ($ total) | 5.30 | 73.06 | 0.99 | 4.79 | 4.04 | 2.78 | 0.30 | 0.01 |
| Slippage ($ total) | 2.69 | 73.06 | 0.99 | 2.45 | 2.09 | 1.48 | 0.30 | 0.01 |
| Longest losing streak (trades) | 6 | 9 | 9 | 6 | 6 | 6 | n/a | n/a |
| Years profitable | 5 of 9 | 5 of 9 | 6 of 9 | 6 of 9 | 5 of 9 | 5 of 9 | 5 of 9 | 5 of 9 |
| Longest time under water (days) | 1303 | 1050 | 1997 | 846 | 846 | 846 | 846 | 846 |
| Worst rolling 12 months | -6.2% | -64.7% | -12.3% | -28.3% | -48.0% | -63.6% | -76.2% | -11.1% |
| First half / 2023+ half return | +16.5% / +7.6% | +114.8% / +246.4% | +11.5% / +7.2% | +19.2% / +56.3% | +23.3% / +125.2% | +29.9% / +230.6% | +43.4% / +410.8% | +1.2% / +15.7% |

Harsh fills, same account:

| Metric | C0 v2 control | C1 trend 100% | C1 trend w* | C3 core 10% + v2 90% | C3 core 25% + v2 75% | C3 core 50% + v2 50% | BTC buy & hold 100% | BTC buy & hold w* |
|---|---|---|---|---|---|---|---|---|
| CAGR | +2.2% | +24.5% | +2.0% | +7.2% | +12.4% | +18.5% | +26.2% | +1.9% |
| Total return | +20.3% | +553.6% | +18.9% | +81.4% | +173.5% | +328.0% | +634.0% | +17.1% |
| Max drawdown | -6.6% | -66.0% | -12.4% | -28.9% | -48.7% | -64.1% | -76.6% | -12.2% |
| Sharpe | 0.67 | 0.72 | 0.48 | 0.54 | 0.57 | 0.63 | 0.69 | 0.37 |
| Calmar | 0.33 | 0.37 | 0.16 | 0.25 | 0.26 | 0.29 | 0.34 | 0.15 |
| Profit factor | 1.89 | 2.52 | 3.80 | 1.89 | 1.89 | 1.96 | n/a | n/a |

2023-onward is contaminated; the first-half / 2023+ row is a consistency check only. Years 2018 and 2026 are partial.

## 4. Calendar-year returns ($300, base fills)

| Year | C0 v2 control | C1 trend 100% | C1 trend w* | C3 core 10% + v2 90% | C3 core 25% + v2 75% | C3 core 50% + v2 50% | BTC buy & hold 100% | BTC buy & hold w* | BTC (price) |
|---|---|---|---|---|---|---|---|---|---|
| 2018 | +0.0% | -35.1% | -1.7% | -6.8% | -17.0% | -34.0% | -67.9% | -1.8% | -67.8% |
| 2019 | +6.1% | +56.5% | +2.6% | +9.1% | +14.6% | +27.5% | +94.3% | +0.8% | +94.3% |
| 2020 | +9.4% | +172.6% | +9.1% | +27.3% | +57.3% | +117.7% | +302.0% | +5.1% | +302.0% |
| 2021 | +0.4% | -22.4% | +1.4% | +11.9% | +25.3% | +41.0% | +59.8% | +3.9% | +59.8% |
| 2022 | +0.0% | +0.0% | +0.0% | -17.7% | -34.3% | -49.7% | -64.2% | -6.4% | -64.2% |
| 2023 | -2.2% | +93.2% | +3.4% | +16.7% | +43.6% | +84.9% | +155.6% | +5.9% | +155.6% |
| 2024 | +11.7% | +79.9% | +3.7% | +40.5% | +68.3% | +95.3% | +121.3% | +11.2% | +121.3% |
| 2025 | -3.7% | -18.4% | -1.0% | -4.8% | -5.5% | -6.0% | -6.3% | -1.2% | -6.3% |
| 2026 | +2.4% | +22.2% | +1.0% | +0.1% | -1.4% | -2.4% | -3.2% | -0.5% | -3.2% |

## 5. Dollar outcomes

Cells: profit per year (final capital, max drawdown). `n/a` = cannot be executed under Binance's minimum order. Full period 2018-2026.

| Strategy | Fills | $25 | $100 | $300 |
|---|---|---|---|---|
| C0 v2 control | base | +1.02 (33.74, -12%) | +3.18 (127.31, -6%) | +8.89 (376.28, -6%) |
| C0 v2 control | harsh | +0.59 (30.06, -14%) | +2.62 (122.44, -6%) | +7.10 (360.91, -7%) |
| C0 v2 control | gap | -0.47 (20.99, -22%) | +1.59 (113.64, -10%) | +4.13 (335.40, -11%) |
| C1 trend 100% | base | +18.76 (185.96, -65%) | +75.06 (743.88, -65%) | +225.25 (2,232.13, -65%) |
| C1 trend 100% | harsh | +16.13 (163.36, -66%) | +64.55 (653.69, -66%) | +193.62 (1,960.80, -66%) |
| C1 trend 100% | gap | +10.94 (118.88, -69%) | +43.57 (473.73, -69%) | +130.71 (1,421.20, -69%) |
| C1 trend w* | base | n/a (below minimum) | n/a (below minimum) | +6.85 (358.74, -12%) |
| C1 trend w* | harsh | n/a (below minimum) | n/a (below minimum) | +6.60 (356.65, -12%) |
| C1 trend w* | gap | n/a (below minimum) | n/a (below minimum) | +5.93 (350.90, -13%) |
| C3 core 10% + v2 90% | base | n/a (below minimum) | +10.32 (188.55, -28%) | +30.22 (559.19, -29%) |
| C3 core 10% + v2 90% | harsh | n/a (below minimum) | +9.25 (179.32, -29%) | +28.48 (544.31, -29%) |
| C3 core 10% + v2 90% | gap | n/a (below minimum) | +8.85 (175.94, -29%) | +25.94 (522.46, -30%) |
| C3 core 25% + v2 75% | base | +4.90 (67.05, -49%) | +20.39 (274.92, -49%) | +62.24 (833.91, -48%) |
| C3 core 25% + v2 75% | harsh | +4.80 (66.19, -49%) | +19.92 (270.85, -49%) | +60.68 (820.46, -49%) |
| C3 core 25% + v2 75% | gap | +4.52 (63.80, -49%) | +19.27 (265.29, -50%) | +58.67 (803.29, -49%) |
| C3 core 50% + v2 50% | base | +9.33 (105.05, -65%) | +38.25 (428.08, -65%) | +115.60 (1,291.58, -64%) |
| C3 core 50% + v2 50% | harsh | +9.19 (103.83, -65%) | +37.75 (423.77, -65%) | +114.73 (1,284.08, -64%) |
| C3 core 50% + v2 50% | gap | +9.23 (104.18, -65%) | +37.48 (421.48, -65%) | +113.54 (1,273.95, -64%) |
| BTC buy & hold 100% | base | +18.47 (183.42, -77%) | +74.05 (735.14, -77%) | +222.31 (2,206.89, -77%) |
| BTC buy & hold 100% | harsh | +18.46 (183.37, -77%) | +73.85 (733.48, -77%) | +221.73 (2,201.89, -77%) |
| BTC buy & hold 100% | gap | +18.47 (183.42, -77%) | +74.05 (735.14, -77%) | +222.31 (2,206.89, -77%) |
| BTC buy & hold w* | base | n/a (below minimum) | n/a (below minimum) | +5.99 (351.34, -12%) |
| BTC buy & hold w* | harsh | n/a (below minimum) | n/a (below minimum) | +5.98 (351.32, -12%) |
| BTC buy & hold w* | gap | n/a (below minimum) | n/a (below minimum) | +5.99 (351.34, -12%) |

## 6. Matched-drawdown comparison

Everything at the control's edge-test drawdown (-12.3%), large account, base fills:

| Strategy | Total return | CAGR | Max DD | Sharpe | Calmar | Years profitable |
|---|---|---|---|---|---|---|
| C0 v2 control (100k at 2% risk) | +57.1% | +5.4% | -12.3% | 0.81 | 0.44 | 5 of 9 |
| C1 200-day trend at w* = 4% | +19.7% | +2.1% | -12.3% | 0.49 | 0.17 | 6 of 9 |
| BTC buy & hold at 3% | +17.3% | +1.9% | -12.3% | 0.37 | 0.15 | 5 of 9 |

Each C3 allocation compared with buy-and-hold and the 200-day rule scaled to **that allocation's own** drawdown ($300, base fills):

| Strategy | Its max DD | Its CAGR / Calmar | 200-day trend at same DD (exposure: CAGR / Calmar) | Buy & hold at same DD (exposure: CAGR / Calmar) |
|---|---|---|---|---|
| C3 core 10% + v2 90% | -28.6% | +7.5% / 0.26 | 15%: +6.5% / 0.23 | 9%: +5.5% / 0.19 |
| C3 core 25% + v2 75% | -48.5% | +12.7% / 0.26 | 44%: +15.9% / 0.33 | 23%: +11.0% / 0.23 |
| C3 core 50% + v2 50% | -64.1% | +18.6% / 0.29 | 97%: +26.0% / 0.41 | 47%: +17.4% / 0.27 |
| C0 v2 control | -6.2% | +2.7% / 0.43 | 2%: +1.0% / 0.16 | 1%: +0.0% / nan |

## 7. Outcome

- **C0 v2 control: HOLD**. Failed: 5a Calmar >= 1.25x control.
- **C1 trend 100%: REJECT**. Failed: 1d ex best 3 trades, 3a max DD <= 15%, 3b worst 12m >= -10%, 3c BTC-down years >= -10%, 5a Calmar >= 1.25x control.
- **C1 trend w*: REJECT**. Failed: 1d ex best 3 trades, 2a executable at $100, 3b worst 12m >= -10%, 5a Calmar >= 1.25x control, 5b harsh Calmar >= control, 5c CAGR >= control.
- **C3 core 10% + v2 90%: REJECT**. Failed: 3a max DD <= 15%, 3b worst 12m >= -10%, 3c BTC-down years >= -10%, 5a Calmar >= 1.25x control, 5b harsh Calmar >= control.
- **C3 core 25% + v2 75%: REJECT**. Failed: 3a max DD <= 15%, 3b worst 12m >= -10%, 3c BTC-down years >= -10%, 5a Calmar >= 1.25x control, 5b harsh Calmar >= control, 6b beats matched C1 by 10%.
- **C3 core 50% + v2 50%: REJECT**. Failed: 2a executable at $100, 3a max DD <= 15%, 3b worst 12m >= -10%, 3c BTC-down years >= -10%, 5a Calmar >= 1.25x control, 5b harsh Calmar >= control, 6b beats matched C1 by 10%, 6c beats core-only by 10%.

**Robustness of the verdict.** No challenger's Calmar (0.41 at best) even reaches the control's own (0.43), let alone the 1.25x bar, so the outcomes do not hinge on the stricter drawdown gates. One quirk of the pre-registered gates: 3b (worst 12 months >= -10%) is stricter than the -12.3% drawdown used for matching, so the matched-exposure variants fail 3b by construction; relaxing it to 15% would change no label because 5a fails for every challenger.

**Implementation caveat.** 'Fixed allocation' was pre-registered as buy once with no rebalancing, so the core's share drifts up in bull runs (a 10% core is roughly 40% of the account at the 2021 peak) and the drawdowns above include that drift. The earlier audit's equal-drawdown comparison used a daily-rebalanced fraction, which is cost-free and flatters passive allocations; that is why it needed 11-14% BTC for the same drawdown while this study needs 3-4%. A periodic-rebalancing design would be a different strategy and needs its own pre-registration.

Parameter counts (G6a): control about 20 tunable settings; C1: 1; C3: control's + 1 (the core share).

Pre-registered selection rule if several qualify: fewest parameters, then smallest BTC share; never highest return.
Candidates: none.