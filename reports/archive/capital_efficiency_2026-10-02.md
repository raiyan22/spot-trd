# Capital efficiency of frozen v2 (2026-10-02)

Frozen v2, BTC spot only, no trade forced, risk per trade never raised: v2's own schedule (2% below 50 USDT, 1% from 50 up). History 2018-03-04 to 2026-10-01 (8.6 years). **Half-edge** means the average trade's edge is halved (the audit found the edge thin and partly flattered); **harsh** uses the harsh fill model. Dollar yardsticks of $10, $50 and $100 a month are references only; what is meaningful to you is your call.

Context: you currently have $25 allocated to the project, the ceiling is $300, additions are exceptional (at most $100 in any single year). The paper experiment runs at $300 to learn from forward results; the table below shows what each capital level would actually have done.

## 1. What each capital level would have produced (base fills)

Profit per year is the average over the whole history at that starting capital. Trades per year, fees and slippage are totals divided by years. Drawdown in dollars is the deepest peak-to-trough fall in account value. 'Setups skipped' is the share of valid v2 setups that could not be traded because the position would fall below Binance's minimum order (5.5 USDT with v2's buffer).

| Capital | Profit / year | Half-edge / year | Harsh / year | Average month | Trades / year | Fees / slippage per year ($) | Max drawdown | Capital in use (avg) | Setups skipped (min order) | Typical position | 95% range of profit / year (edge uncertainty) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| $25 | $+1.02 | $+0.51 | $+0.59 | $+0.08 | 4.8 | 0.09 / 0.05 | $3 (-12.3%) | 4% | 47% | $10 | $-0.4 to $+2.7 |
| $50 | $+1.22 | $+0.61 | $+0.82 | $+0.10 | 4.9 | 0.10 / 0.05 | $3 (-6.3%) | 2% | 44% | $11 | $-0.5 to $+3.1 |
| $75 | $+1.92 | $+0.96 | $+1.46 | $+0.16 | 5.5 | 0.15 / 0.07 | $5 (-6.5%) | 2% | 25% | $13 | $-0.4 to $+4.5 |
| $100 | $+3.18 | $+1.59 | $+2.62 | $+0.26 | 5.9 | 0.21 / 0.11 | $6 (-6.1%) | 2% | 1% | $17 | $-0.3 to $+6.7 |
| $125 | $+3.92 | $+1.96 | $+3.16 | $+0.32 | 5.9 | 0.26 / 0.13 | $8 (-6.1%) | 2% | 0% | $21 | $-0.4 to $+8.3 |
| $150 | $+4.45 | $+2.22 | $+3.86 | $+0.37 | 5.9 | 0.31 / 0.16 | $9 (-6.1%) | 2% | 0% | $25 | $-0.6 to $+9.7 |
| $200 | $+5.92 | $+2.96 | $+4.68 | $+0.49 | 5.9 | 0.41 / 0.21 | $12 (-6.2%) | 2% | 0% | $34 | $-0.8 to $+13.0 |
| $300 | $+8.89 | $+4.45 | $+7.10 | $+0.73 | 5.9 | 0.62 / 0.31 | $19 (-6.2%) | 2% | 0% | $51 | $-1.2 to $+19.5 |
| $325 | $+9.60 | $+4.80 | $+7.71 | $+0.79 | 5.9 | 0.67 / 0.34 | $20 (-6.2%) | 2% | 0% | $56 | $-1.4 to $+21.1 |
| $350 | $+10.34 | $+5.17 | $+8.25 | $+0.85 | 5.9 | 0.72 / 0.37 | $22 (-6.2%) | 2% | 0% | $60 | $-1.5 to $+22.7 |
| $400 | $+11.85 | $+5.93 | $+9.48 | $+0.98 | 5.9 | 0.83 / 0.42 | $25 (-6.2%) | 2% | 0% | $68 | $-1.7 to $+26.0 |
| $500 | $+14.81 | $+7.40 | $+11.83 | $+1.22 | 5.9 | 1.03 / 0.52 | $31 (-6.2%) | 2% | 0% | $86 | $-2.1 to $+32.5 |

Return on capital is about 2.7% a year at $300 and does not rise with more capital: profit scales with capital because risk per trade is a fixed percentage of the account. The one real exception is the small account. At $25, v2 runs at 2% risk and cannot trade 47% of its setups; at $50 it falls back to 1% risk and still skips 44%; from about $100 up almost every setup is tradable (1% skipped). That is a tradability effect, not an income effect.

## 2. What would another $100 of capital add?

| Change | Profit per year | Extra profit per year (base) | Half-edge | Harsh | Years of extra profit to repay the extra $100 (base) | Extra drawdown in dollars |
|---|---|---|---|---|---|---|
| $25 to $125 | $+1.02 to $+3.92 | $+2.90 | $+1.45 | $+2.57 | 34 years | $+5 |
| $100 to $200 | $+3.18 to $+5.92 | $+2.73 | $+1.37 | $+2.07 | 37 years | $+6 |
| $300 to $400 | $+8.89 to $+11.85 | $+2.96 | $+1.48 | $+2.38 | 34 years | $+6 |
| $400 to $500 | $+11.85 to $+14.81 | $+2.95 | $+1.48 | $+2.35 | 34 years | $+6 |

## 3. Capital needed for reference incomes at v2's return on capital

| Income yardstick | Per year | Capital needed (base) | Capital needed (half-edge) | Capital needed (harsh) |
|---|---|---|---|---|
| $10 a month | $120 | $4,484 | $8,967 | $5,509 |
| $50 a month | $600 | $22,418 | $44,837 | $27,545 |
| $100 a month | $1,200 | $44,837 | $89,673 | $55,090 |

Capital that does not exist in your situation: even $700 (the most you could reach by 2030 with $300 plus $100 a year) is a small fraction of these.

## 4. Research horizon 2030, with annual additions

Trade-level simulation (20,000 paths) of the observed trade results, trades arriving at v2's observed rate for each capital band, plus an extra deposit on each anniversary of 2026-10-02 (first on 2027-10-02). Additions are **not** profit: all profit figures are trading P&L = final account value minus start minus everything deposited. No circuit breaker, so it ignores v2's pauses. Horizons: end of 2029 = 3.25 years, end of 2030 = 4.25 years.

### By the end of 2029

| Start | Additions | Total put in | Trading profit, base: median (5th to 95th pct) | Half-edge | Harsh | Profit in the last 12 months, base median | Half-edge median | Chance of trading profit below zero (base) |
|---|---|---|---|---|---|---|---|---|
| $25 | none | $25 | $+2 ($-3 to $+13) | $+1 ($-4 to $+10) | $+1 ($-3 to $+10) | $+0.1 | $-0.3 | 27% |
| $25 | +$25/yr | $100 | $+4 ($-4 to $+18) | $+2 ($-7 to $+15) | $+3 ($-5 to $+14) | $+0.4 | $-0.4 | 25% |
| $25 | +$50/yr | $175 | $+6 ($-5 to $+27) | $+2 ($-9 to $+22) | $+4 ($-6 to $+22) | $+1.5 | $-0.1 | 24% |
| $25 | +$100/yr | $325 | $+10 ($-8 to $+46) | $+4 ($-15 to $+38) | $+8 ($-9 to $+41) | $+3.1 | $-0.1 | 24% |
| $100 | none | $100 | $+7 ($-6 to $+29) | $+3 ($-9 to $+23) | $+6 ($-6 to $+25) | $+1.0 | $-0.3 | 21% |
| $100 | +$25/yr | $175 | $+10 ($-6 to $+37) | $+4 ($-12 to $+30) | $+8 ($-7 to $+33) | $+2.0 | $-0.1 | 20% |
| $100 | +$50/yr | $250 | $+12 ($-8 to $+46) | $+4 ($-14 to $+37) | $+9 ($-9 to $+40) | $+2.5 | $-0.2 | 20% |
| $100 | +$100/yr | $400 | $+16 ($-11 to $+65) | $+6 ($-20 to $+52) | $+12 ($-13 to $+57) | $+4.0 | $-0.0 | 22% |
| $300 | none | $300 | $+24 ($-13 to $+87) | $+10 ($-26 to $+70) | $+19 ($-15 to $+76) | $+4.1 | $+0.0 | 18% |
| $300 | +$25/yr | $375 | $+26 ($-15 to $+96) | $+10 ($-29 to $+76) | $+21 ($-17 to $+83) | $+4.7 | $-0.0 | 18% |
| $300 | +$50/yr | $450 | $+28 ($-16 to $+105) | $+11 ($-31 to $+82) | $+22 ($-18 to $+91) | $+5.1 | $-0.2 | 18% |
| $300 | +$100/yr | $600 | $+32 ($-20 to $+124) | $+13 ($-37 to $+99) | $+25 ($-22 to $+108) | $+7.1 | $-0.0 | 19% |

### By the end of 2030

| Start | Additions | Total put in | Trading profit, base: median (5th to 95th pct) | Half-edge | Harsh | Profit in the last 12 months, base median | Half-edge median | Chance of trading profit below zero (base) |
|---|---|---|---|---|---|---|---|---|
| $25 | none | $25 | $+3 ($-3 to $+16) | $+1 ($-5 to $+12) | $+2 ($-3 to $+12) | $+0.1 | $-0.3 | 22% |
| $25 | +$25/yr | $125 | $+7 ($-5 to $+25) | $+3 ($-9 to $+20) | $+5 ($-6 to $+21) | $+1.1 | $-0.3 | 20% |
| $25 | +$50/yr | $225 | $+10 ($-6 to $+41) | $+4 ($-12 to $+32) | $+8 ($-7 to $+34) | $+2.2 | $-0.1 | 19% |
| $25 | +$100/yr | $425 | $+19 ($-11 to $+73) | $+8 ($-22 to $+58) | $+15 ($-13 to $+64) | $+4.3 | $-0.2 | 18% |
| $100 | none | $100 | $+10 ($-6 to $+36) | $+4 ($-11 to $+28) | $+8 ($-7 to $+31) | $+1.2 | $-0.2 | 17% |
| $100 | +$25/yr | $200 | $+15 ($-7 to $+49) | $+6 ($-14 to $+38) | $+12 ($-8 to $+43) | $+2.4 | $-0.1 | 15% |
| $100 | +$50/yr | $300 | $+18 ($-9 to $+64) | $+8 ($-19 to $+51) | $+14 ($-10 to $+56) | $+3.0 | $-0.3 | 16% |
| $100 | +$100/yr | $500 | $+27 ($-14 to $+98) | $+11 ($-28 to $+77) | $+21 ($-16 to $+86) | $+5.6 | $-0.3 | 17% |
| $300 | none | $300 | $+33 ($-12 to $+107) | $+14 ($-28 to $+83) | $+26 ($-15 to $+93) | $+3.9 | $-0.2 | 14% |
| $300 | +$25/yr | $400 | $+36 ($-14 to $+121) | $+15 ($-33 to $+94) | $+29 ($-17 to $+105) | $+4.9 | $-0.2 | 14% |
| $300 | +$50/yr | $500 | $+41 ($-17 to $+135) | $+17 ($-37 to $+105) | $+33 ($-20 to $+118) | $+6.2 | $+0.0 | 14% |
| $300 | +$100/yr | $700 | $+49 ($-21 to $+167) | $+21 ($-46 to $+130) | $+39 ($-25 to $+146) | $+7.9 | $-0.2 | 15% |

## 5. Verdict

- **Is the strategy economically worth continuing at your capital?** As an income source, no. At $300 it produced about $8.89 a year ($4.45 if the edge is half, $7.10 with harsh fills), with a worst fall of about $19. At $25 it produced about $1.02 a year and could not trade 47% of its setups. As a low-cost forward test of whether the historical edge is real, it is cheap: about $0.6 a year in fees at $300, and nothing is at risk in paper mode.
- **Would another $100 materially change the economics?** No. At v2's return on capital (about 2.7% a year) an extra $100 adds roughly $3 a year (about $1.3 if the edge is half) and a few dollars more drawdown; it would take about 37 years of that extra profit to repay itself. The one practical benefit of capital is tradability: moving from $25 toward $100 removes the minimum-order skipping, but even that is worth only a couple of dollars a year. I do not recommend adding capital for the sake of the account growing slowly.
- **Can it become a meaningful income by 2030?** Not on this evidence. Even with $300 plus $100 every year (total $700 put in by 2030), the median trading profit by the end of 2030 is about +$49 in total and about +$8 in the final year in the base case; the half-edge case is lower, and there is a real chance the profit is below zero (see the tables). Adding $100 a year raises the 2030 median profit by only about +$17 relative to adding nothing. A $10 a month yardstick ($120 a year) needs roughly $4,484 at this return.
- **What this does not say:** it does not say the strategy is worthless as a controlled learning exercise, and it does not rule out that forward results differ from history. It says that no capital level inside your constraints turns this edge into income, and that raising risk to compensate was already rejected on probability of loss.
