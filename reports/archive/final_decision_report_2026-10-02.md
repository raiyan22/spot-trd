# Final decision report: halal BTC spot system (spot-trd)

2026-10-02. Consolidates five studies: the profitability audit, the small-universe and Sharia study, the challenger comparison, the
higher-risk study, and the intraday study. Detail and sources are in the reports named under each heading. All dollars are USDT.
Every study after the audit had its acceptance criteria written and hashed **before** results existed; v2 and the files it depends
on have been frozen since 2026-10-02 08:10 UTC (`tests/test_freeze.py` enforces it).

## 1. Bottom line

1. **v2 is a capital-preserving practice tool, not an income source.** On $25 it earns about **$1 a year** ($0.60 to $1.70 depending on
   fill assumptions); on $300 about **$7 to $9 a year**. Its edge is thin and unproven.
2. **Nothing I tested beats it in a way that meets your own priorities** (robustness, realistic execution, controlled drawdown,
   forward expectancy, meaningful return, simplicity): not more assets, not a 200-day trend rule, not a core-plus-tactical mix, not
   higher risk, not intraday trading.
3. **Bigger dollars come only from more capital, more time, or more drawdown.** The $300 to $350 in 3 to 6 months target is rejected.
4. **Keep v2 frozen in paper mode, BTC only.** Forward paper results are the only untouched evidence you have, and at about 6 trades a
   year they accumulate slowly.

## 2. What was found, study by study

### A. Profitability audit (`audit_2026-10-02.md`, `v3_decision_report_2026-10-02.md`)
- **Code and data:** no look-ahead or leakage (85 truncation dates, every feature identical); data clean; sizing correct (every stop-out
  costs exactly -1R).
- **Two optimistic fill assumptions fixed:** exits that were decided on a close now fill at the next open with slippage, and a limit buy
  must be traded through, not touched. Cost: edge-test return +58.4% became +57.1%. Fees and slippage are now tracked per trade.
- **Unfixable biases (disclosed):** BTC was picked in hindsight; about 30 rule variants were judged on one history; 2023-onward is
  contaminated (v2 was designed after v1 failed on the whole history); the FOMC/CPI entry block exists only in the live card and has
  never been backtested.
- **Edge:** 50 trades, 42% win rate, +0.65R average, profit factor 2.1, max drawdown -12.3% (edge test, base fills). **Three trades make
  78% of the profit**; without them the other 47 average +0.15R. Bootstrap interval for mean R [+0.02, +1.38]; once the ~30 variants
  tried are accounted for, the nominal p of 2% is not credible. Walk-forward annual re-selection: +13.6% over 2021-2026 (2.2% a year).
  Random entries inside the same gate earn a median +33.7% against v2's +57%, so most of the return comes from the trend gate and the
  trailing exit, with some from entry timing.
- **Fill sensitivity (edge-test return):** base +57.1%, harsh +46.1%, stops filling 1.5% worse than planned +14.0% (and $25 falls to
  $20.99). Hourly candles on the 48 stop-out days: median in-hour drop below the stop 0.49%; in 23 of 48 the drop exceeded the 0.5%
  stop-limit band within the hour, so a stop-limit can fail to fill in fast moves.
- **Dollars:** $25 ends 8.6 years at $33.74 (+35%, -12.3% drawdown), $1.02 a year; harsh $0.59; 2023-onward $1.67. $300 earns $8.89 a
  year (harsh $7.10). 47 of 101 setups at $25 were skipped because the position fell below Binance's 5.5 USDT minimum. In any single
  year a $25 account ends below its start about 48% of the time. Capital needed for $1 a day: about $13.6k to $27k at 1% risk, about
  $6.8k at 2%.
- **Reference points:** BTC buy-and-hold turned $25 into $184 (-77% drawdown); an all-in 200-day-trend rule into $287 (-65%).

### B. Small universe and Sharia screening (`universe_2026-10-02.md`, `sharia_screening_2026-10-02.md`)
- Same v2 rules on BTC, ETH, SOL, ADA, LTC with one shared account, position caps of 1 to 3, total risk held at the single-asset budget.
  Pre-registered test (more trades, 1.25x return, controlled drawdown, consistency): **no universe passes**. Annualized return stays near
  +2.5% (BTC alone 2.5%); trades roughly double. BTC+ETH alone is worse on drawdown. BTC+ETH+SOL with 3 slots cut drawdown (-8.0% vs
  -12.7%) at the same return, which is diversification, not more return. At $300 the best multi-asset case earned about $0.70 more a
  year. At $25 a second position cannot clear the minimum order.
- **Sharia:** documented, not decided. The sources are mostly commercial aggregators that contradict each other; the one primary
  methodology paper (SRB, 2018) allows utility tokens "provided that the project is Shariah compliant", which is exactly the part you
  must judge for platform tokens. Lending-type protocols are about 24% of non-exchange DeFi value on Ethereum and 17% on Solana. Only
  BTC is `approved` in `config/sharia_screen.yaml`; a test fails if a tradable symbol is not.

### C. Challenger comparison (`challenger_preregistration_2026-10-02.md`, `challengers_2026-10-02.md`)
- Control v2, a BTC 200-day trend rule (all-in and drawdown-matched), and core 10/25/50% + v2, judged against fixed gates, no ranking by return.
- Look-ahead checks passed on real data, including a deliberate leak that inflated 1,000 to 174,043 versus 7,442 for the correct pipeline.
- **No challenger qualifies:** control HOLD, all five challenger configurations REJECT. Drawdowns: core 10/25/50% was -29%/-49%/-64%; the
  all-in trend rule -65%. No challenger's return per unit of drawdown (Calmar 0.41 at best) reached v2's 0.43.
- Dollars at $300 over the period: v2 +$8.89 a year (-6% drawdown), core 10% +$30 (-29%), all-in trend +$225 (-65%). More money is only
  more risk. At $25 a 10% core ($2.50) cannot even be bought.
- **Correction of my own earlier claim:** I said a 10-14% BTC allocation matched v2 at equal drawdown. That used a cost-free,
  daily-rebalanced fraction. Implemented as buy-once, the matching exposure is 3-4% and returns +17-20% against v2's +57% at the same
  drawdown. So "complexity adds nothing" was too strong; what holds is that v2 and the all-in trend rule have about the same return per
  unit of drawdown (0.43 vs 0.41), so the real choice is how much risk to carry.

### D. Higher-risk v2 (`risk_modes_preregistration_2026-10-02.md`, `risk_modes_2026-10-02.md`)
- Target: $300 to $350 (+16.7%) in 3 to 6 months. **Rejected.** At 1%/2%/3%/5% risk per trade, the 6-month chance of reaching it was
  0%/2%/19%/24%, against a 50% bar; the chance of ending below the start was about 41-42% at every level; at 5% the 5th-percentile
  window lost about 11% and the worst about 15%.
- Arithmetic: v2 makes about 3 trades in 6 months with a median trade of -0.35R, so the average case needs about **9% risk per trade**
  (18% for 3 months). A spot position can lose at most its stop distance, a median about 5%. The target is out of reach even all-in.
- A paper test cannot validate any higher-risk mode: telling +0.65R per trade from zero needs about 112 trades, about **19 years** at
  v2's trade rate.
- Caveats: only about 17 independent 6-month windows exist; 12- and 24-month rows are noise.

### E. Intraday strategies (`intraday_preregistration_2026-10-02.md`, amendment 1, `intraday_2026-10-02.md`)
- Three predefined long-only 1-hour strategies (opening-range breakout, gated pullback-reclaim, Bollinger mean reversion), one entry a
  day at most, flat before 23:00, no trade forced, 0.31% round-trip cost. **All three lose after costs:** mean net R -0.10, -0.15, -0.23;
  gross moves +0.13%, +0.06%, -0.04% against 0.31% of costs per trade. $300 ended at $62, $119, $155 with drawdowns of -84%, -66%, -49%.
- The best (breakout) would need about 0.13% round-trip costs to break even, below even Binance's fee alone at the standard rate.
- Verification: causality checks passed. My pre-registered leak check was ill-posed for the mean-reversion strategy, and my first
  replacement had no power (0 of 4 detections); I fixed it openly in an amendment and the final planted-leak check caught 3, 4 and 6
  of 8 cuts. A leak can only flatter results, so it could not be hiding a profit.

## 3. Mistakes on my side that you should know about

- The audit's first "complexity adds nothing" conclusion relied on a flattering rebalancing assumption (corrected in section C).
- The first hourly stop check was degenerate (always 0%); fixed to measure in-hour drops.
- A relabelled "v1" research candidate was actually v2; a "harsh" scenario briefly pointed at the wrong row; a day-number bug under
  pandas 3 broke the intraday day logic. All were caught by checking the output or by tests and fixed before conclusions were drawn.
- The first intraday leak check and its first replacement were both flawed, as described above.

## 4. What is supported and what is not

**Supported by the evidence**
- Keep v2 frozen, paper mode, BTC only, circuit breakers on (on: +57% vs off: +49% with a shallower drawdown).
- Use the harsh fill numbers for planning, and the expectation of about $1 a year on $25.
- A market stop-loss, or at least a wider stop-limit band, for sells (the hourly evidence). Not implemented because it changes the frozen
  live card; it needs your decision.

**Not supported; do not build**
- More assets, more positions, higher risk per trade, a dollar-target risk multiplier, intraday spot trading at retail fees, a
  200-day or core-plus-tactical replacement, the best row of any ablation, tuning the S&P-gate lookback, wider trails of 4 ATR or more,
  Fear & Greed or MVRV filters, Laya. Treating 2023-onward as a clean holdout. Treating the FOMC/CPI block as validated.

## 5. Decisions only you can make

1. **Purpose of the money.** Practice and capital preservation (the current system fits), or absolute dollars (requires more capital or
   more drawdown than you have said you will accept).
2. **Risk appetite.** The studies show returns scale with BTC exposure and drawdown roughly together. If you want a fixed constant
   BTC share with periodic rebalancing, that is a different design and needs its own criteria written first.
3. **Sell-order type** on the live card (market stop vs stop-limit). Requires a new freeze record if you approve a change.
4. **Sharia approvals** for ETH, SOL, ADA, LTC in `config/sharia_screen.yaml`, if you want any researched further. BTC remains the only
   enabled asset until you say otherwise.
5. **FOMC/CPI block:** backtest it with historical dates, or keep it as a judgment call.

## 6. What would change this conclusion

- **Forward paper results** of v2 from 2026-10-02: a year shows only gross breakage (about 6 trades); expectancy needs about 19 years.
- **More capital**: at $2k to $7k the same strategy produces meaningful dollars at the same risk per trade.
- **A different source of edge** (not a tweak of price indicators), tested under pre-registered gates with realistic costs.

## 7. File index (`F:\ryn\spot-trd\reports`)

| Topic | Files |
|---|---|
| Audit | `audit_2026-10-02.md`, `v3_decision_report_2026-10-02.md`, `research_2026-10-02.md` |
| Universe / Sharia | `universe_2026-10-02.md`, `sharia_screening_2026-10-02.md`, `config/sharia_screen.yaml` |
| Challengers | `challenger_preregistration_2026-10-02.md`, `challengers_2026-10-02.md`, `challenger_freeze_2026-10-02.json` |
| Higher risk | `risk_modes_preregistration_2026-10-02.md`, `risk_modes_2026-10-02.md`, `risk_modes_freeze_2026-10-02.json` |
| Intraday | `intraday_preregistration_2026-10-02.md`, `..._amendment_1_...md`, `intraday_2026-10-02.md`, `intraday_2026-10-02_run1_as_first_produced.md`, `intraday_freeze_2026-10-02.json` |
| This report | `final_decision_report_2026-10-02.md` |

Commands: `uv run spot audit`, `uv run spot universe`, `uv run python -m spot_trd.challengers`, `...risk_modes`, `...intraday`;
`uv run pytest -q` (103 tests).
