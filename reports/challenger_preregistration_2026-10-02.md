# Challenger study: pre-registration

Written 2026-10-02, **before any challenger code was written or any challenger result was computed.** The SHA-256 of this file
and of the live-strategy files is recorded in `reports/challenger_freeze_2026-10-02.json` at the same moment. Nothing below may
be edited after results exist; if a mistake is found, it gets a dated amendment at the bottom and the original text stays.

## 0. What this study is and is not

- It decides only whether a challenger is **worth forward paper-testing alongside v2**. It cannot promote anything to live
  trading, and it cannot declare a winner by return.
- The live paper strategy (v2, `config/rules.yaml` and the files hashed in the freeze file) stays frozen so that paper results
  from 2026-10-02 on are genuine forward evidence. A test fails if those files change.
- One BTC price path (2018-2026) cannot establish an edge. A pass means "not ruled out", never "proven".
- Prior knowledge, disclosed: the 2026-10-02 audit already showed roughly that a ~14% BTC allocation matched v2's return at
  equal drawdown, and that the 200-day rule had a -65% drawdown all-in. The thresholds below were set from principles
  (noise level, user's stated priorities), not tuned to produce an outcome, but this study is not blind.
- 2023-onward is contaminated (v2 was designed and judged using it). It is shown as a consistency check, never as a holdout.
- BTC is the only asset. Sharia screening is untouched and independent of every result here.

## 1. The three challengers (rules fixed now; no parameter is searched)

**C0, control: v2 BTC-only.** `rules.yaml` unchanged, conservative fills as in the audit.

**C1, BTC 200-day trend.** The target is "in BTC" while the last completed daily close is above its 200-day simple moving average
(period fixed at 200, mean of the last 200 completed daily closes), otherwise USDT. The signal known at the close of day t
executes at the open of day t+1 as a market order. Position size is fixed at entry as a fraction of account equity and is not
rebalanced while held. Exposures reported: **100%** (as specified) and **w\*** (the single matched-drawdown exposure, defined in
section 3).

**C3, core + tactical.** A fixed share f of the starting account buys BTC once (market order at the next open) and is held with
no rebalancing; the rest runs C0 on its own capital. f is **10%, 25% and 50%** only. All three are always reported.

Reference (not a challenger): BTC buy-and-hold, at 100% and at w\*.

## 2. Execution framework (identical for every strategy)

- Fee 0.1% per side. Market fills at the next open with adverse slippage. Binance minimum order 5 USDT x 1.1 on every entry; if
  a position cannot reach it the strategy is **not executable** at that capital and is reported as such, not scaled up. Lot size
  0.00001 BTC.
- Scenarios: **base** (v2's base fills; market-type slippage 0.1%), **harsh** (market-type slippage 0.3%; for v2 also 0.15%
  limit trade-through and 0.5% stop slippage), **gap stress** (all exits and stops fill 1.5% worse than planned).
- Capital points: $25, $100, $300 with v2's risk schedule inside any v2 sleeve. The gates are evaluated at **$300** (every
  configuration is executable there); $25 and $100 are reported for the user's real decision.
- Period: 2018-03-04 to 2026-10-01 (v2's first possible signal date; the 200-day SMA is computed on full history so it is ready
  by then). Halves: before and after 2023-01-01.

## 3. Matched-drawdown rule (not an optimisation)

w\* is the one BTC exposure at which C1's full-period maximum drawdown (large account, base fills, executed with the same
fixed-at-entry sizing) equals the control's edge-test maximum drawdown (v2, 100,000 USDT at 2% risk, base fills). It is
computed once by bisection and used for C1 and for buy-and-hold. For C3, which cannot be tuned to a drawdown, buy-and-hold and
C1 are scaled to C3's own drawdown for comparison. Note this uses the full-sample drawdown, a hindsight quantity, so it supports
*comparison* only; it is not a rule anyone could have followed in advance.

## 4. Metrics reported for every configuration

CAGR, calendar-year returns and share of years profitable (2018 and 2026 are partial years and flagged), maximum drawdown,
longest time under water, Sharpe (daily returns, sqrt(365), zero risk-free rate), Calmar (CAGR / |max DD|), profit factor and
trades per year (round trips; "n/a" where a strategy has none), time invested, fees, slippage, capital utilisation (BTC value
over equity), longest losing streak, dollar outcomes at $25 / $100 / $300 under base, harsh and gap stress, comparison with
BTC buy-and-hold, and the matched-drawdown comparison.

## 5. Look-ahead verification (must pass before results are read)

1. The SMA at day t equals the mean of the closes of days t-199..t and nothing later.
2. **Perturbation test:** replace every bar after a random cut date with different prices; the equity curve up to and including
   the cut must be unchanged, for C1 at 100% and w\*, for the core, and for C3.
3. **Leak detector:** a deliberately leaked variant (acting on day t's signal at day t's open) must score visibly better than the
   correct pipeline; if it does not, the test has no power and is not trusted.
4. No rebalancing: the number of BTC held is constant between an entry and its exit.
5. Exposure fixed at entry from equity known at that open; never from later equity.

## 6. Acceptance criteria

Evaluated in the stated priority order. **G1-G4 are hard gates: failing any one rejects the configuration.** G5 and G6 decide
whether a configuration that passed the hard gates is worth the extra forward-testing effort.

**G1 Robustness** (all required)
- 1a. Total return > 0 in each half of the history (before 2023, 2023 onward), base fills.
- 1b. Harsh-fill full-period CAGR is positive and at least 60% of the base CAGR.
- 1c. Over rolling 3-year windows starting every 91 days (harsh fills): at least 75% of windows have a positive return and the
  worst window is no worse than -10%.
- 1d. Remove the best 3 round-trip trades (for C3: the best 3 tactical trades): total profit still >= 0, base fills.

**G2 Realistic execution** (all required)
- 2a. Executable at $100: no component blocked by Binance's minimum order, and at most 30% of v2 setups skipped for size.
- 2b. Gap-stress full-period total return > 0.

**G3 Controlled drawdown** (all required, at $300, base and harsh)
- 3a. Maximum drawdown <= 15%.
- 3b. Worst rolling 12-month return >= -10%.
- 3c. Return in each BTC-down calendar year (2018, 2022) >= -10%.

**G4 Forward-looking expectancy** (all required for Stage 1)
- 4a. 2023-onward half: CAGR > 0 under both base and harsh fills (a consistency check; the period is contaminated).
- 4b. No parameter was chosen from results: exposures and allocations are the ones declared in section 1, and the freeze hashes match.
- 4c. **Stage 2, forward:** no live use unless at least 12 months of forward shadow results since 2026-10-02 show return >= 0 and
  maximum drawdown <= 15%. Stage 1 can never satisfy this.

**G5 Meaningful economic return** (vs the control, at $300, full period, base unless stated)
- 5a. Calmar >= 1.25 x the control's Calmar. (1.25x because with about 50 trades the confidence interval on v2's average R is
  roughly +/-100%, so smaller differences cannot be told from noise.)
- 5b. Harsh-fill Calmar >= the control's harsh-fill Calmar.
- 5c. Base CAGR >= the control's base CAGR at the same capital (a lower-risk copy of the control does not count).
- Dollars at $25 / $100 / $300 are always reported. No gate can make $25 meaningful; the study will say so if true.

**G6 Simplicity and complexity-must-pay**
- 6a. Parameter count is reported (control: about 20 tunable settings; C1: 1; C3: control's + 1).
- 6b. A challenger with more moving parts than C1 must beat C1 at matched drawdown by >= 10% in harsh-fill Calmar.
- 6c. C3 must also beat core-only buy-and-hold at its own drawdown by >= 10% in harsh-fill Calmar (the tactical sleeve must add
  value beyond simply holding the same BTC).

**Outcome labels**
- **REJECT:** fails any of G1-G4(a,b).
- **HOLD:** passes G1-G4(a,b) but fails G5 or G6. Not worth forward-testing now.
- **FORWARD-TEST CANDIDATE:** passes G1-G4(a,b), G5 and G6. Goes to paper shadow-tracking next to v2; Stage 2 (4c) still required before any live use.
- The control is graded by the same gates for information. Whatever its grade, it stays the live paper strategy until forward
  evidence says otherwise.

**No ranking by return.** The report lists pass/fail per gate. If several configurations are candidates, the recommendation is
the one with the fewest parameters, then the smallest BTC share. If none is a candidate, the report says so plainly and no new
layer of complexity is added.

## 7. Planned execution

Freeze file written first. Then the challenger module and the look-ahead tests. Results are read only after the look-ahead tests
pass. The forward window starts 2026-10-02; the same code, re-run on data after that date, produces the forward result.
