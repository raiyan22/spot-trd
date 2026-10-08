# Intraday BTC study results (2026-10-02)

Pre-registration: `intraday_preregistration_2026-10-02.md` (frozen 2026-10-02T08:37:14+00:00); frozen files unchanged: **YES**. Binance BTC/USDT 1h, 2018-03-04 to 2026-10-02 (75,136 candles, 28 gaps over 1 hour). Long-only spot, one entry per UTC day at most, flat before 23:00, no trade forced. A small set of 1h candles around 48 stop-out days had been downloaded earlier for a different purpose (stop slippage); no intraday strategy was run on them.

## 1. Look-ahead verification (before results are read)

- Indicators at a candle equal their value computed from candles up to it only: **PASS**.
- Perturbation: after 4 random cut dates every later candle was replaced by different prices; the list of trades that exit by the cut (entry time, exit time, return) is identical for A, B and C: **PASS**.
- Leak detector (acting on a candle's signal at that same candle's open): mean net return per trade, correct vs leaked: A -0.166% vs +0.734%, B -0.253% vs +0.269%, C -0.353% vs -1.782%: **FAIL (no power)**.
- Daily gates use the previous completed day only (a gate that is True only on day D first applies at 2022-03-12, D+1): **PASS**.
- Schedule: no entry after the 20:00 open, none held overnight, at most one entry a day (violations: 0): **PASS**.

All checks passed: **NO: results below must not be trusted**.

## 2. Expectancy per trade (net of costs; large account so Binance's minimum never binds)

| Strategy | Trades | Per year | Days traded | Win rate | Gross / trade | Costs / trade | Net / trade | Mean net R | Median R | Profit factor | Corrected lower bound (mean R) | Harsh mean R | Break-even cost / base cost |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A. Opening-range breakout | 1652 | 193 | 53% | 40% | +0.1% | -0.3% | -0.2% | -0.097 | -0.20 | 0.80 | -0.145 | -0.184 | 0.42x |
| B. Gated pullback-reclaim | 618 | 72 | 20% | 29% | +0.1% | -0.3% | -0.3% | -0.153 | -0.37 | 0.66 | -0.233 | -0.234 | 0.18x |
| C. Mean reversion | 294 | 34 | 9% | 38% | -0.0% | -0.3% | -0.4% | -0.226 | -0.82 | 0.56 | -0.332 | -0.323 | -0.12x |

Exits: A: {'time': 1107, 'stop': 545}; B: {'time': 262, 'signal': 228, 'stop': 128}; C: {'stop': 147, 'time': 95, 'target': 52}

## 3. Stability and drift

| Strategy | Mean R: before / after 2022-07-01 | Years with positive mean R | Random-entry net / trade | Strategy net / trade | Share of random runs beaten |
|---|---|---|---|---|---|
| A. Opening-range breakout | -0.065 / -0.129 | 2 of 9 | -0.263% (95th pct -0.189%) | -0.183% | 98% |
| B. Gated pullback-reclaim | -0.082 / -0.211 | 2 of 7 | -0.245% (95th pct -0.146%) | -0.253% | 44% |
| C. Mean reversion | -0.236 / -0.218 | 0 of 8 | -0.251% (95th pct -0.108%) | -0.353% | 13% |

Calendar-year mean net R (2018 and 2026 partial):

| Year | A. Opening-range breakout | B. Gated pullback-reclaim | C. Mean reversion |
|---|---|---|---|
| 2018 | -0.187 | +nan | -0.382 |
| 2019 | +0.020 | +0.088 | -0.155 |
| 2020 | +0.160 | -0.104 | -0.369 |
| 2021 | -0.113 | -0.138 | -0.156 |
| 2022 | -0.274 | +nan | +nan |
| 2023 | -0.028 | -0.319 | -0.294 |
| 2024 | -0.117 | -0.219 | -0.138 |
| 2025 | -0.176 | -0.149 | -0.236 |
| 2026 | -0.161 | +0.402 | -0.145 |

## 4. The $300 account (1% risk, capped at 98% of cash)

| Strategy | Fills | Final capital | CAGR | Max DD | Profit per year ($) | Sharpe | Fees / slippage ($) | Longest losing streak | Skipped (minimum order) |
|---|---|---|---|---|---|---|---|---|---|
| A. Opening-range breakout | base | 62.46 | -16.7% | -84.0% | -27.68 | -1.31 | 312.31 / 184.23 | 12 | 0 |
| A. Opening-range breakout | harsh | 14.43 | -29.8% | -95.3% | -33.28 | -2.87 | 148.10 / 261.06 | 18 |  |
| B. Gated pullback-reclaim | base | 118.74 | -10.2% | -66.1% | -21.12 | -1.35 | 139.97 / 79.01 | 12 | 0 |
| B. Gated pullback-reclaim | harsh | 70.06 | -15.6% | -78.2% | -26.80 | -2.42 | 97.29 / 164.63 | 14 |  |
| C. Mean reversion | base | 154.58 | -7.4% | -48.8% | -16.95 | -1.42 | 78.13 / 45.57 | 9 | 0 |
| C. Mean reversion | harsh | 115.26 | -10.5% | -61.7% | -21.53 | -2.23 | 58.34 / 102.98 | 9 |  |

## 5. Pre-registered gates

| Gate | A. Opening-range breakout | B. Gated pullback-reclaim | C. Mean reversion |
|---|---|---|---|
| N1 >= 300 trades | PASS 1652 | PASS 618 | **FAIL** 294 |
| N2 corrected lower bound > 0 | **FAIL** -0.145 (p = 1.000) | **FAIL** -0.233 (p = 1.000) | **FAIL** -0.332 (p = 1.000) |
| N3 harsh R > 0 and break-even >= 1.5x | **FAIL** -0.184, 0.42x | **FAIL** -0.234, 0.18x | **FAIL** -0.323, -0.12x |
| N4 both halves > 0 and >= 6 of 9 years | **FAIL** -0.065/-0.129, 2 yrs | **FAIL** -0.082/-0.211, 2 yrs | **FAIL** -0.236/-0.218, 0 yrs |
| N5 beats 95th pct of random entries | PASS -0.183% vs -0.189% | **FAIL** -0.253% vs -0.146% | **FAIL** -0.353% vs -0.108% |
| N6 CAGR >= 5%, DD <= 15%, harsh profitable | **FAIL** -16.7%, -84.0%, harsh -29.8% | **FAIL** -10.2%, -66.1%, harsh -15.6% | **FAIL** -7.4%, -48.8%, harsh -10.5% |
| **Outcome** | **NO EDGE** | **NO EDGE** | **NO EDGE** |

## 6. Verdict

- **A. Opening-range breakout: NO EDGE.** Mean net R -0.097 per trade (gross move +0.133%, costs 0.316% per trade).
- **B. Gated pullback-reclaim: NO EDGE.** Mean net R -0.153 per trade (gross move +0.057%, costs 0.310% per trade).
- **C. Mean reversion: NO EDGE.** Mean net R -0.226 per trade (gross move -0.038%, costs 0.315% per trade).

Positive expectancy after realistic costs demonstrated: **none**.
Three strategies were tested, so significance was corrected for three; no parameter was changed after the first run.