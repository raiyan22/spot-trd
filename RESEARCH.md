# spot-trd research record

Everything that was tested, what it showed, what was decided and why, in one place. Dated 2026-10-02 (research phase 2026-10-01 to 2026-10-02).
Detailed tables behind every section are in `reports/archive/` (reproducible with the commands in section 15). Frozen
pre-registrations and their hashes are in `reports/` (section 14). All dollars are USDT.

**Contents**
1. Status in one page
2. The brief: constraints, priorities, capital, decisions log
3. Strategy v2 (the frozen strategy)
4. Phase 1: building v2, the research grid, Laya, literature upgrades, tools
5. Phase 2: the profitability audit
6. Small universe and Sharia screening
7. Challenger study (200-day trend, core + tactical)
8. Higher-risk study ($300 to $350 in 3-6 months)
9. Intraday study
10. $300 to $350 feasibility
11. Capital efficiency and the 2030 horizon
12. Limit-buy / execution comparison
13. Decisions and records (sell orders, Sharia status, autostart, Benner)
14. Pre-registration and freeze register
15. Corrections and mistakes log
16. Everything rejected or not supported
17. Limits of the evidence, and what would change the conclusions
18. Reproduce: commands to archived reports
Appendix A: Sharia screening notes (full)
Appendix B: Sell-order decision record (full)

---

## 1. Status in one page

| Item | State |
|---|---|
| System | Halal BTC/USDT **spot-only** decision support for Binance. It tells you when/where to place limit buys, where to put the stop, when to sell; you place orders by hand. No API keys, no auto-trading. |
| Strategy | **v2, frozen.** Pullback entries in a confirmed uptrend, trailing stop, trend-break exit. Files hashed in `reports/*freeze*.json`; `tests/test_freeze.py` fails if they change. |
| Mode | **FORWARD OBSERVATION.** v2 is the experiment. No new strategy or execution research without the user's explicit approval. |
| Experiment | Paper growth: **$300 start, no contributions, target $350 from trading P&L only**, started 2026-10-02. Milestones $310/320/330/340/350 count realized equity only. Run `uv run spot growth`. |
| Monitor | Running in paper mode, autostart ON (how to stop/start: guide section 2). |
| Assets | BTC only. ETH/SOL/ADA/LTC documented but **not approved** (user leans "probably" ETH, SOL, ADA; not final). |
| Verdict in one sentence | v2 has a thin, unproven edge; it earns about **$1/yr on $25 and about $9/yr on $300**; nothing tested beats it under the user's priorities; $350 is a multi-year outcome with no honest deadline; more capital does not change the economics. |
| Open decisions for the user | Purpose of the money (practice vs income); whether to test a periodically rebalanced "core BTC + trend" design; final Sharia approvals; whether to start Benner-cycle or other new research. |

---

## 2. The brief

**User's goals.** A halal, spot-only BTC/USDT decision-support system on Binance. Never lose the capital, minimise losses, compound gains slowly, profit short and long term, with clear daily decisions: what to buy, when, limit prices, how long to hold. Factors requested: BTC 1M/1D/4H, S&P 500, gold, oil, DXY, historical pattern analysis. Multiple limit buys/sells allowed; strategy choice delegated to Claude.

**Hard constraints (never weakened).** Spot only: no leverage, futures, options, margin, short selling. Zero interest (riba): no Earn/staking/lending, no yield products. BTC/USDT only unless the user approves another asset. `halal_guard.py` enforces this.

**Risk the user approved (2026-10-01).** 2% per trade while equity is under 50 USDT, then 1%. Circuit breakers: 3 losses in a row = 7-day pause; 5% below peak equity = 30-day pause.

**Process preferences.** Use uv. Use the RTX 3060 for model work. No Windows notifications (a local HTML dashboard refreshed every 5 minutes instead). No visible terminal window for the background process. Robust, precise, straightforward, key analytics present. "Forget about committing, build first": no commit prompts.

**Capital situation (stated 2026-10-02).** $25 actually allocated; **$300 is the maximum committable**; possible additions of $25-$50, **never more than $100 in any single year, no more often than yearly, exceptional only** and never to be counted as trading profit. 2030 is a research horizon, not a promise. The user does not want a fake deadline and would rather abandon a weak strategy than build on a backtest illusion.

**Standing instructions from later requests.** Do not force trades, add assets because they backtest well, chase a daily dollar target, raise risk to hit a target, overfit, or optimise toward $350. Pre-register criteria **before** testing anything new, and never crown the best-backtest configuration. 2023-onward is contaminated (v2 was designed after v1 failed on the whole history) and must never be presented as a clean holdout. Sharia screening is separate from performance. A manual limit buy before a v2 plan exists is a different strategy and is not allowed: wait for the frozen signal.

**Decisions log**

| Date | Decision |
|---|---|
| 2026-10-01 | Risk schedule 2%/1% approved. Laya skipped (see 4.4). Dashboard instead of Windows notifications; hidden monitor. |
| 2026-10-02 | Fill model made conservative (exits at next open, limit buys need a trade-through). v2 and its files frozen at 08:10 UTC. BTC stays the only asset. |
| 2026-10-02 | Paper-growth experiment started: $300, no contributions. Old $25 paper journal archived (`journal/archive/`). |
| 2026-10-02 | Sell-order type: user delegated; **market stop** chosen for capital preservation (Appendix B). Autostart turned ON. |
| 2026-10-02 | Sharia: user "probably" wants ETH, SOL, ADA; recorded as a lean only (`user_lean`), `user_decision` stays pending. Concern noted: a fixed $300 shared with other assets. |
| 2026-10-02 | Benner cycle raised as possible separate research: not started (section 16). |

---

## 3. Strategy v2 (frozen)

Rules live in `config/rules.yaml` (version 2). The system decides **only on completed daily candles**; live prices are context and alerts, never triggers.

| Part | Rule |
|---|---|
| Regime gate | All must hold: BTC above its 10-month SMA (1M); daily close above EMA200 and EMA50 above EMA200 (1D); macro calm (S&P 500 above its 50-day SMA, DXY not up more than 2.5% in 20 days, not both gold +6% and oil +10% in 20 days). |
| Entry setup | Daily close within 1% above EMA20 (or below it), still above EMA50, RSI14 below 55. |
| Orders | Two equal-notional limit buys at signal close - 0.25 ATR and - 0.75 ATR, valid 2 daily bars, unfilled orders cancelled. |
| Stop | Lowest entry price minus 1 ATR; as soon as any buy fills, a protective sell is placed (now a **market stop**, section 13). |
| Exits | 2-ATR chandelier trailing stop (stop only ever moves up); sell at market if the 1M/1D trend breaks; no profit target, no maximum holding time. |
| Sizing | Worst-case loss at the stop inside the risk budget (2% under 50 USDT, 1% above); 98% maximum cash use; every order and the position valued at the stop must clear Binance's 5 USDT minimum x 1.1 buffer (otherwise the setup is skipped); lot step 0.00001 BTC. |
| Breakers | 3 consecutive losses = 7-day pause; equity 5% below peak = 30-day pause. |
| Event filter | No new entries on or the day before FOMC/CPI dates (`config/events.yaml`; add next year's dates each autumn). **Live card only; never backtested.** |
| Fees | 0.1% per side, no BNB discount assumed. |

**Backtest fill assumptions (conservative, `rules.yaml` `execution`).** A decision made on a daily close is only known at that close, so regime/time exits fill at the **next open** with 0.1% slippage. A resting limit buy fills only if the day's low trades **0.05% through** it (touching is not a fill) or the bar opens at/below it. Stops fill at min(stop, open) less 0.1% slippage; inside a bar the stop is assumed to trigger before any target. "Harsh" = 0.15% trade-through, 0.3% exit slippage, 0.5% stop slippage. "Gap stress" = stops fill 1.5% worse than the position was sized for.

---

## 4. Phase 1: building v2 (2026-10-01)

### 4.1 v1 had no edge
v1 (fixed targets TP 1.5R/3R, 10-day maximum hold, no trend exit) earned about nothing: in the research grid its in-sample (2018-22) return was +4.2% and 2023+ +0.6%.

### 4.2 The research grid (21 variants)
Variants ranked by in-sample (2018-2022) return/max drawdown, requiring at least 10 trades and in-sample drawdown within 10% (a cap added after the in-sample winner turned out overfit). 100,000 USDT at 2% risk. Selected: **pullback, stop 1.0 ATR, 2-ATR trail, no TP, regime exit.**

| Variant (edge test) | 2018-22 | 2023+ |
|---|---|---|
| **Selected: stop 1.0 ATR, trail 2.0 ATR, TP1 off** | 23 trades, +0.87R, +34.6%, DD -7.0% | 27 trades, +0.47R, +17.7%, DD -9.6% |
| Stop 1.5 ATR, trail 2.0 | +24.1%, DD -5.1% | +16.1%, DD -7.1% |
| Trend 20-day breakout, 2 ATR | +34.6%, DD -7.7% | +8.3%, DD -7.3% |
| v1 fixed targets | +4.2%, DD -5.7% | +0.6%, DD -5.2% |
| Trail 4 ATR, TP1 off (in-sample "winner") | **+123.5%**, DD -17.9% | **-8.6%**, DD -18.8% |
| Trail 4 ATR, stop 1.5, TP1 off | +81.3%, DD -16.9% | +5.2%, DD -8.7% |

Wide trails (4-5 ATR) looked best in sample and failed out of sample: a textbook overfit, so they were excluded by the drawdown cap and are rejected. Later audit note: the first grid row in the saved report was labelled "v1" but was actually v2 (a labelling bug in `research.py`, fixed; the walk-forward in section 5 includes a genuine v1).

### 4.3 What the first backtest said (as first published, before the conservative fill fixes)
Buy-and-hold BTC over the same period: +626%, max drawdown -76.6%.

| | Edge test (100k at 2%) | Your account ($25, schedule) |
|---|---|---|
| Final equity | 158,375 (+58.4%) | 33.94 (+35.8%) |
| CAGR / max drawdown | +5.5% / -11.6% | +3.6% / -11.7% |
| Trades | 50 (plans 61, unfilled 11) | 41 (plans 53, unfilled 12) |
| Win rate / avg R / median R | 42% / +0.65 / -0.34 | 36.6% / +0.43 / -0.46 |
| Profit factor / time in market | 2.16 / 16% | 1.89 / 11.3% |
| Exits | trail 37, stop 11, regime 2 | trail 30, stop 9, regime 2 |
| Setups skipped for minimum order | none | **47** |
| Circuit-breaker halts | 10 | 8 |

Early vs recent (edge test): 2018-22 23 trades +34.6% (DD -7.0%); 2023+ 27 trades +17.7% (DD -9.6%).
Edge-test years: 2018 0 trades, 2019 +11.9%, 2020 +19.2%, 2021 +0.9%, 2022 0 trades (the gate kept it out while BTC fell about 64%), 2023 -4.4%, 2024 +23.6%, 2025 -4.9%, 2026 +4.8%.

**Forward BTC returns by regime (2018-now, 10-day horizon):** all days mean +1.2% (54% up); regime OK +2.0% (53% up, 20-day median -0.1%); setup days +1.8% (54% up; 20-day mean +4.4% but median -0.5%); regime blocked +0.7%; macro risk-off +0.4%. The gate adds a little, not a lot.

**Holding periods (backtest):** 0-7 days = 40% of trades at -0.47R (quick stop-outs); 8-20 days = 48% at +0.44R; 21+ days = 12% at **+5.23R, about 96% of profit.** Cutting losers fast pays for letting the few big trends run; taking quick profits early removes exactly the trades that make the money.

### 4.4 Laya (open-source "System 1" classifier) evaluation: SKIPPED
Question: does zero-shot Laya improve decisions beyond the rules? Target: is BTC higher 10 days later? Calibrated on 2018-22, judged on 2023-01-01 to 2026-09-20 (1,359 days), on the RTX 3060 (cuda).

| Signal | AUC (0.5 = coin flip) | 95% interval |
|---|---|---|
| Laya outlook | 0.497 | 0.427 to 0.560 |
| Laya "buy now?" | 0.527 | 0.457 to 0.588 |
| Rules: regime gate | 0.474 | 0.417 to 0.538 |
| Information ceiling (logistic regression on the same numbers) | 0.544 | 0.468 to 0.605 |

Rank correlation of the Laya score with the actual 10-day return: -0.014. Filtering signals by Laya improved 2018-22 (+0.87R to +1.16R) but not 2023+ (+0.47R to +0.62R with return unchanged +17.7% to +17.5%), i.e. no robust gain. Speed was never the issue (Laya ~19 ms per decision, rules ~0.003 ms). **Verdict: skip.** Even a model trained directly on these numbers cannot rank unseen outcomes better than chance, so fine-tuning on the same information is very unlikely to help. Re-test only with genuinely new inputs.

### 4.5 Literature upgrades tested and rejected (2026-10-02)
Adoption rule fixed before running: beat the baseline's return/max-drawdown in **both** 2018-22 and 2023+, keep at least half the trades in each period, and do not deepen the $25 account's drawdown. **No variant passed.**

| Idea | Source | 2018-22 return/DD | 2023+ return/DD | Result |
|---|---|---|---|---|
| Baseline v2 | | 4.92 | 1.84 | |
| Skip entries at Fear & Greed >= 75 | alternative.me contrarian research | 5.12 | 1.50 | worse 2023+ |
| Enter only at Fear & Greed <= 50 | same | 6.09 (+1.31R) | **-1.00** (-0.80R, 8 trades) | textbook overfit |
| Skip entries at MVRV >= 3 | Grobys et al. 2026 (rests on 3 trades) | 4.22 | 1.84 | almost never triggers; slightly worse |
| 20-day Donchian-midpoint trailing exit | Zarattini et al. 2025 | -0.37 (+0.01R) | 1.87 | smoother, ~0 profit 2018-22 |
| Donchian-ensemble trend gate | Zarattini et al. 2025 | 5.63 | 1.30 | worse 2023+, deeper small-account DD |

Not tested: funding rates (R^2 about 0.003 in the literature, a perpetual-futures mechanism we do not use) and intraday ML (a GitHub study found 0 of 159k configurations profitable on 1-15 minute bars after fees).

### 4.6 Tools built
Card (`spot today`) with a one-line decision, live price context and chart; always-on monitor and dashboard; append-only journal with paper/live separation and a halal guard (refuses unplanned buys, oversells, buys beyond cash); `spot validate` (data health, Binance limits, strategy decay, live vs backtest bands); `spot review` (execution mistakes: chased entry, late stop, discretionary exit, late regime exit); `spot decisions` (every daily decision logged with reason and inputs, compared with what BTC did 5/10/20 days later, showing which rule caused missed rallies or avoided drops).

---

## 5. Phase 2: the profitability audit (2026-10-02)

Question: is the strategy economically viable once methodology is fixed and costs are realistic?

### 5.1 Code and data audit
| Check | Result |
|---|---|
| Look-ahead / leakage | **None.** Every feature and signal rebuilt from data truncated at 85 dates matched the full-data values. Macro timing is safe (S&P/DXY/gold/oil close before the BTC daily close). |
| Data integrity | Clean: no gaps, duplicates or bad prices in 3,333 daily bars; oil's negative print (Apr 2020) is clipped. |
| Regime exit | Was optimistic (sold at the same close that revealed the signal, no slippage). **Fixed:** next open with slippage. |
| Limit buys | Was optimistic (touch = fill). **Fixed:** 0.05% trade-through. |
| Costs | Now tracked per trade (fees and slippage). |
| Sizing | Correct: every stop-out loses exactly -1R in the base case. |
| Stop-limit realism | The weak point (see 5.3). |
| Not fixable | Selection bias (BTC picked in hindsight; about 30 rule variants judged on one history); contaminated 2023+; the FOMC/CPI filter was never backtested. |

### 5.2 What each assumption was worth (edge test, then the $25 account)
| Fill model | Edge return | Edge max DD | Avg R | $25 final |
|---|---|---|---|---|
| 0. As first published | +58.4% | -11.6% | +0.65 | 33.94 |
| 1. + exits at next open, 0.1% slip | +58.3% | -11.6% | +0.65 | 33.93 |
| 2. + 0.05% limit trade-through = **base (now default)** | **+57.1%** | -12.3% | +0.65 | 33.74 |
| 3. + stop slippage 0.3% | +50.7% | -12.6% | +0.60 | 31.80 |
| 4. **Harsh** | +46.1% | -12.2% | +0.57 | 30.06 |
| 5. **Gap stress** (stops 1.5% worse than sized) | **+14.0%** | -20.0% | +0.30 | **20.99** (worst trade -1.52R) |

The engine fixes cost little; the **edge is very sensitive to stop fills**.

### 5.3 Stop slippage evidence
On the 48 stop-type exit days the daily low was a median 1.08% below the stop (90th percentile 6.85%). Hourly candles on those days: within the first hour that traded through the stop, the hour's low was a median **0.49%** below it (mean 0.90%, 90th percentile 2.00%, worst 7.68%); in **23 of 48** cases price fell more than the 0.5% stop-limit band within that single hour, and in **2** the hour closed below the limit price. So a stop-limit can sit unfilled in fast drops. (A first version of this check was degenerate, always 0%; fixed. Section 15.) This led to the market-stop decision (section 13).

### 5.4 Is there an edge?
Edge test, base fills: 50 trades, win rate 42%, average +0.65R (median -0.35R), profit factor 2.1, max drawdown -12.3%.
- **Three trades make 78% of the profit** (best +8.9R; top 3 = +25.4R of +32.5R). Without them the other 47 average **+0.15R**, roughly zero after costs. Win rate 42%; 9 trades above +2R.
- Bootstrap 95% interval for mean R: full [+0.02, +1.38]; development 2018-22 [+0.00, +1.89] (23 trades); 2023+ [-0.35, +1.54] (27 trades). About 30 variants were judged on the same history, so the nominal p of 2% is not credible (a crude correction puts it near 60%).
- **Walk-forward** (each January pick the best of the variants using only earlier data): +13.6% over 2021-2026 (2.2% a year), max DD -13.0%; fixed v2 over the same years +17.8%. The chosen variant changed (three different ones across six years): selection is unstable.
- **Placebo** (300 runs, random entry days inside the same gate): median +33.7% against v2's +57.1%; the real pullback signal beat 83% of random runs on return, 84% on return/DD, 100% on average R. So most return comes from the trend gate and trailing exit, with some from entry timing.
- **Parameter neighbours** (28 one-step changes): 27 profitable, range **+7% to +75%**, median +47.9% vs base +57.1%. Fragile spots: S&P gate lookback 100-day instead of 50-day = +6.9%; RSI cap 45 = -1.3% (10 trades); order valid 1 day = +12.9%; pullback EMA 30 = +15.5%; trail 1.5 ATR = +24.9%.
- **Ablation** (16 combinations of gates and pullback timing): component choices change return by large amounts both ways (the 1M-only rows earn more than the full rule set at similar drawdown). That is noise from 50-140 trades; switching to the best row now would be in-sample selection and is rejected.
- **Circuit breakers on vs off:** +57.1% vs +49.2% with DD -12.3% vs -13.7%. Keep them.
- **Other coins with the same untuned rules (a one-off exploratory pass, not used for decisions):** average R ETH +0.64, BNB +0.82, DOGE +1.06, LTC +0.07, SOL +0.02, XRP -0.01, LINK -0.06, ADA -0.16. BTC is among the best-looking, so BTC's result is probably flattered.

Calendar years (edge test, base fills, with BTC's own return): 2018 0% (BTC -68%); 2019 +11.9% (+94%); 2020 +19.2% (+302%); 2021 +0.8% (+60%); 2022 0% (-64%); 2023 -5.1% (+156%); 2024 +23.6% (+121%); 2025 -4.9% (-6%); 2026 +4.8% (-3%). Average exposure only 3-9%.

### 5.5 Baselines (same period, same costs) and the correction
| Approach | Total return | CAGR | Max DD | Calmar |
|---|---|---|---|---|
| Stay in USDT | 0% | 0% | 0% | n/a |
| BTC buy and hold ($25 to $184) | +636% | +26.2% | -76.6% | 0.34 |
| Simple trend: BTC above 200-day SMA else USDT ($25 to $287) | +1,047% | +32.9% | -64.7% | 0.51 |
| Strategy's own gate held all-in | +771% | +28.7% | -66.2% | 0.43 |
| v2 on $25 (schedule) | +35.0% | +3.6% | -12.3% | 0.29 |
| v2 edge test | +57.1% | +5.4% | -12.3% | 0.44 |

Risk-appetite frontier for the 200-day rule with a fraction of the account in BTC (daily-rebalanced, cost-free approximation): 10% = +36.8% (DD -8.9%, $25 to $34); 25% = +112.6% (DD -21.2%); 50% = +310.5% (DD -38.8%); 100% = +1,047% (DD -64.7%). **Correction (made later, see section 7):** an early claim that "a 10-14% BTC holding matches v2 at equal drawdown, so complexity adds nothing" used this cost-free daily-rebalanced fraction. Implemented as buy-once, the matching exposure is only 3-4% and returns +17-20% against v2's +57% at the same drawdown.

### 5.6 Economics by capital (base fills, full period, v2's risk schedule)
| Capital | Profit/yr | Avg month | Trades/yr | Max DD | Setups skipped (min order) |
|---|---|---|---|---|---|
| $25 | $1.02 | $0.08 | 4.8 | -12.3% ($3) | 47% |
| $50 | $1.22 | $0.10 | 4.9 | -6.3% | 44% |
| $100 | $3.18 | $0.26 | 5.9 | -6.1% | 1% |
| $300 | $8.89 | $0.73 | 5.9 | -6.2% ($19) | 0% |
Harsh fills: $25 $0.59/yr; $300 $7.10/yr. Out-of-sample 2023+: $25 $1.67/yr, $300 $7.13/yr. Fees about $0.09/yr at $25 and $0.62/yr at $300. Median month is exactly $0 (about 97% of days have no trade). Flat 2% risk instead: $300 earns about $19.9/yr (CAGR 5.4%, DD -12%).

**Monte Carlo ($25, resampled trades).** One year: median $25.09 (5th-95th $23.37-$30.88), **48% chance of ending below the start**; three years median $27.17. Half-edge: 57% below start after one year; no-edge: 63%. Streaks: median 2, worst-5% 5 over one year.

**Capital for $1/day ($365/yr):** about $13.6k (full period), $18.4k (2023+), $27.3k (halved edge) at 1% risk; about $6.8k at 2% risk.

### 5.7 Audit verdict (questions A-G)
- **A. Genuine edge?** Weak and unproven; trend-following on BTC is plausible but this evidence is thin (3 trades = 78% of profit; true expectancy more likely near half the backtest).
- **B. After costs?** About $1/yr on $25, $9/yr on $300 (base); $0.59 and $7.10 harsh.
- **C. Is $25 meaningful?** No.
- **D. Meaningful capital?** Thousands of dollars (section 11).
- **E. Expand beyond BTC?** No (section 6).
- **F. Supported changes:** conservative fill model (done); expectations reset (done); keep BTC-only and the circuit breakers; a market stop for sells (done, section 13); treat the FOMC/CPI block as unvalidated.
- **G. Not supported:** all rejected ideas (section 16).

---

## 6. Small universe and Sharia screening

**Test (pre-registered before running).** Same v2 rules and parameters on BTC, ETH, SOL, ADA, LTC, one shared account, position caps 1-3, total risk held at the single-asset budget (`equal`: each slot gets 1/k of it; `heat`: a new position gets what open stops have not used). Assets served in a fixed order (BTC, ETH, SOL, ADA, LTC), LTC chosen as fifth on screening grounds before any result (an exploratory eight-coin pass had already been run once; LTC turned out among the weakest). A universe "materially improves" only if ALL hold versus BTC alone on the same window: trades per year at least 1.5x; annualised return at least 1.25x and positive under harsh fills; max drawdown no more than 25% deeper and losing streak no more than 2 trades longer; no worse return in both halves. Window 2021-02 to 2026-10 (SOL's history).

**Result: no universe passes** (0 of 18 configurations pass the return test).

| Universe, max positions | Trades/yr | CAGR | Max DD | Avg R |
|---|---|---|---|---|
| BTC alone (reference) | 6.3 | +2.5% | -12.7% | +0.35 |
| BTC+ETH, 1 | 7.9 | +1.8% | -17.5% | +0.15 |
| BTC+ETH, 2 | 12.0 | +1.3% | -11.5% | +0.25 |
| BTC+ETH+SOL, 3 | 13.6 | +2.5% | -8.0% | +0.33 |
| BTC+ETH+SOL+ADA, 2 | 14.5 | +2.7% | -11.3% | +0.19 |
| 5 assets, 2 | 15.6 | +2.7% | -9.4% | +0.19 |

Trades roughly double but return does not rise; BTC+ETH alone worsens drawdown; BTC+ETH+SOL with 3 slots lowers drawdown at the same return (diversification, not more return, and it fails the return test). At $300 the best multi-asset case earned about $0.70 more a year (BTC alone $3.5/yr, best $4.2/yr on the window). At $25 a second position is untradable (1% per slot is $0.25 of risk, under the minimum order). Each asset alone with the same rules (edge test): BTC +0.65R, ETH +0.64R, SOL +0.02R (17 trades), ADA -0.16R, LTC +0.07R. **BTC stays the only asset.**

**Sharia screening** is documented in Appendix A (methodology, per-asset notes, source-quality warnings). Only BTC is `approved` in `config/sharia_screen.yaml`; a test fails if a tradable symbol lacks an approved record. Status of the user's view: a lean ("probably ETH, SOL, ADA"), **not** an approval.

---

## 7. Challenger study (pre-registered)

Control v2, a BTC 200-day-SMA trend rule (100% and drawdown-matched), and core 10/25/50% + v2 (core bought once, no rebalancing). Gates fixed before any code (G1 robustness, G2 realistic execution, G3 drawdown <= 15%, G4 forward-looking expectancy, G5 Calmar >= 1.25x control, G6 complexity must pay). Look-ahead checks passed on real data; the deliberate leak inflated 1,000 to 174,043 against 7,442 for the correct pipeline.

| | v2 control | Trend 100% | Trend matched | Core 10% + v2 | Core 25% + v2 | Core 50% + v2 |
|---|---|---|---|---|---|---|
| CAGR ($300) | 2.7% | 26.4% | 2.1% | 7.5% | 12.7% | 18.6% |
| Max drawdown | -6.2% | -64.7% | -12.3% | -28.6% | -48.5% | -64.1% |
| Calmar | 0.43 | 0.41 | 0.17 | 0.26 | 0.26 | 0.29 |
| Dollars/yr at $300 | +8.89 | +225 | +6.9 | +30 | +62 | +116 |
| Outcome | **HOLD** | REJECT | REJECT | REJECT | REJECT | REJECT |

Matched exposure (no rebalancing): 4.3% in BTC for the 200-day rule, 2.7% for buy-and-hold, each giving the control's -12.3% drawdown; those return +19.7% and +17.3% against v2's +57.1%. No challenger's Calmar reaches v2's, so the outcomes do not hinge on the stricter drawdown gates (one quirk: gate 3b, worst 12 months >= -10%, is stricter than the -12.3% used for matching, so matched variants fail it by construction; relaxing it changes no label). Core drifts upward in bull runs (a 10% core is about 40% of the account at the 2021 peak). At $25 a 10% core ($2.50) cannot be bought. **Correction of the earlier audit claim:** see 5.5. What stands: v2 and the all-in trend rule have about the same return per unit of drawdown (0.43 vs 0.41), so the real choice is how much risk to carry. A periodically rebalanced fixed allocation is a different design and would need its own pre-registration.

---

## 8. Higher-risk study ($300 to $350 in 3-6 months)

Pre-registered multiples 1x/2x/3x/5x of the 1% schedule (1%/2%/3%/5% per trade); "bounded" means at most 3%. Acceptance R1 reach >= 50%, R2 loss <= 20%, R3 P(DD >= 20%) <= 10%, R4 5th percentile >= -15% and worst >= -25%, R5 history agrees with Monte Carlo, R6 risk <= 3%. **Target rejected.**

- v2 makes about 5.8 trades a year (about 3 in 6 months), median trade -0.35R, SD 2.45R; the average case needs about **9% risk per trade for 6 months (18% for 3 months)**. A spot position can lose at most its stop distance (median about 5%, 10th percentile 3.3%), so the required risk is out of reach even all-in. Required pace about 36%/yr (6 months) or 85%/yr (3 months) against v2's 5.4%/yr at 2% risk.
- Rolling 6-month windows from $300, base fills: reach +16.7% at 1x/2x/3x/5x = **0%/2%/19%/24%** (bar 50%); end below start about 41-42% at every level; 5th percentile -2.5%/-5.0%/-8.3%/-10.6%, worst -4.1%/-6.7%/-12.0%/-15.1%; harsh fills worse. Monte Carlo agrees (5x: 26%). 3-month reach: 0%/0%/7%/12%.
- A paper test cannot validate any higher-risk mode: about **112 trades, about 19 years** at v2's rate to separate +0.65R from zero.
- Caveats: only about 17 independent 6-month windows; the 12/24-month rows are non-monotonic because breakers fire more often at high risk (noise); R2 as written is strict (v2 ends a 6-month window slightly below start in about 40% of windows even at 1x) but R1 alone rejects every multiple.

---

## 9. Intraday study (pre-registered)

Three predefined long-only spot strategies on BTC/USDT 1-hour candles, 2018-03 to 2026-10 (75,136 candles), decisions at a candle's close, execution at the next open, one entry per UTC day at most, flat before the 23:00 open, no trade forced. Costs: 0.10% fee per side plus slippage (base round trip about 0.31%); harsh slippage higher. Significance corrected for three strategies.

| Strategy | Trades | Days traded | Gross/trade | Net/trade | Mean net R | $300 end (base) |
|---|---|---|---|---|---|---|
| A. Opening-range breakout (00-03 UTC range, 0.5% minimum width) | 1,652 | 53% | +0.13% | -0.18% | -0.10 | $62 (DD -84%) |
| B. Gated pullback-reclaim (v2 daily gate + 1h EMA20/50) | 618 | 20% | +0.06% | -0.25% | -0.15 | $119 (DD -66%) |
| C. Mean reversion (Bollinger 20,2 + RSI14 < 30, 200-day gate) | 294 | 9% | -0.04% | -0.35% | -0.23 | $155 (DD -49%) |

**All three: NO EDGE.** Every corrected lower bound is negative; harsh costs stay negative; A and B had only 2 positive calendar years (C none); C also fell below the 300-trade minimum. A passes the random-entry gate only by being less negative (-0.18% vs -0.19%), which is not an edge. A would need about 0.13% round-trip cost to break even (Binance's fee alone is 0.20%, 0.15% with the BNB discount, before slippage). Verification: causality checks passed. The pre-registered leak-direction check was ill-posed for the mean-reversion strategy (buying at the signal candle's open is a worse price) and the first replacement had no power (0 of 4 detections); both are documented in `reports/intraday_preregistration_amendment_1_2026-10-02.md` (the first run is preserved in the archive); the final planted-leak check caught 3, 4 and 6 of 8 cuts. A leak can only flatter results, so it could not hide a profit.

---

## 10. $300 to $350 feasibility (frozen v2, realized equity only)

- Evidence: 51 trades in 8.6 years (5.9/yr), win rate 41%, average +0.47% of equity per trade, median -0.34%. Profit/yr at $300: base **$8.89**, harsh $7.10, gap stress $4.13, 2023+ $7.13.
- **Arithmetic years to +$50:** base 5.6, harsh 7.0, half-edge 11.2, gap 12.1, no edge never. Bootstrap 95% interval of the mean trade -0.07% to +1.09% of equity ($-1.2 to +$19.5/yr at $300): the low end is below zero.
- **Simulation (20,000 paths, no breaker): probability of having reached $350 realized within**

| Scenario | 1y | 2y | 3y | 5y | 10y | Median time (among those that get there) |
|---|---|---|---|---|---|---|
| base | 3% | 11% | 22% | 45% | 80% | 4.5 y |
| conservative (half the edge) | 2% | 7% | 14% | 27% | 53% | 4.9 y |
| harsh fills | 2% | 8% | 17% | 36% | 72% | 5.0 y |
| gap stress | 2% | 7% | 14% | 28% | 56% | 4.9 y |
| no edge | 1% | 4% | 8% | 15% | 28% | 4.7 y |

- Median years to each milestone, base: $310 1.2, $320 2.1, $330 3.0, $340 3.8, $350 4.5.
- **Being below $300 (realized):** base 39% of paths after 1 year, 26% after 2, 20% after 3, 12% after 5; half-edge 50/41/36/30%; no edge about 55% persistently. Worst-5% drawdown within 5 years -8.6% (base), -13.1% (half-edge).
- Historical path (start 2018-03): reached $350 realized after 3.0 years and never fell below $300 (a favourable start). Across all start dates only 31% had reached $350 by the end of the data; fastest 1.7 years; none within a year; marked equity spent a median 12% of days below $300 (worst start 100%); longest stretch below $300 reached 3.6 years; the equity curve once went 1,303 days (3.6 years) without a new high. Max drawdown -6.2% (about $19), harsh -6.6%, gap -10.5%.
- **There is no honest deadline.** If the edge is close to history, $350 is a multi-year outcome; if half, decade-long; if illusory, no reason to expect it. A paper test cannot tell these apart quickly (about 112 trades, about 19 years).

---

## 11. Capital efficiency and the 2030 horizon

Return on capital is about **2.7% a year at any size** because risk per trade is a fixed percentage of the account.

| Capital | Profit/yr | Half-edge | Harsh | 95% range of profit/yr (edge uncertainty) |
|---|---|---|---|---|
| $25 | $1.02 | $0.51 | $0.59 | -$0.4 to +$2.7 |
| $100 | $3.18 | $1.59 | $2.62 | -$0.3 to +$6.7 |
| $300 | $8.89 | $4.45 | $7.10 | -$1.2 to +$19.5 |
| $500 | $14.81 | $7.40 | $11.83 | -$2.1 to +$32.5 |

- **Another $100 adds about $3/yr** ($1.3 if half-edge) and about $6 more drawdown; it would take about **34-37 years** of that extra profit to equal the extra $100. The only real benefit of capital is tradability: $25 cannot trade 47% of setups, $50 44%, $75 25%, $100 about 1%. Do not add capital merely because growth is slow.
- **Capital for reference incomes** at v2's return: $10/month needs about $4,500 (base; $9,000 half-edge); $50/month about $22,400; $100/month about $44,800.
- **2030 horizon** (simulation with a deposit at each anniversary of 2026-10-02; deposits are not profit): median trading profit by end 2030 with **$300 + $100/yr (total put in $700): +$49** (half-edge +$21, harsh +$39; 5th-95th -$21 to +$167); $300 with no additions +$33; $25 + $100/yr (total $425) +$19; chance of trading profit below zero by 2030 about 14-22%. Adding $100/yr raises the 2030 median by only about $17. Median profit in the final 12 months about +$8 at best. **Not a meaningful income by 2030 on this evidence.**

---

## 12. Limit-buy / execution comparison (pre-registered)

Scope: only how the **same frozen v2 signals** are executed. A manual limit buy before a v2 card issues a plan is a different strategy and is not allowed (default: wait for the frozen signal; when a card says BUY, place its own two limit orders, which already are a limit-entry method). Large account, base fills.

| Method | Plans | Fill rate | Mean R per filled | Mean R per signal | Entry vs next open | Total return | Max DD | Calmar |
|---|---|---|---|---|---|---|---|---|
| **M0 v2 ladder (2 limits)** | 62 | 81% | +0.650 | **+0.524** | +1.6% better | +57.1% | -12.3% | 0.44 |
| M1 market at next open | 54 | 100% | +0.370 | +0.370 | -0.2% | +44.8% | -12.2% | 0.36 |
| M2 one limit at close - 0.5 ATR | 82 | 49% | +0.629 | +0.307 | +2.2% better | +57.8% | -16.7% | 0.33 |

Harsh fills: M0 +46.1% (Calmar 0.37), M1 +18.9% (0.13), M2 +45.6% (0.28). Non-fills: M0 missed 12 plans (19%, about +9R under market entry); M2 missed 42 (51%, about +8.6R). Alternatives vs M0: gain per signal -0.154R (M1) and -0.218R (M2), bootstrap lower bounds negative, Calmar and half-period tests failed, M2 fill rate 49% < 70%. **No alternative passed; keep M0.** $300 account: M0 $8.89/yr, M1 $8.16, M2 $9.27 (but DD -9.0%).

---

## 13. Decisions and records

- **Sell-order type (2026-10-02):** the user delegated; I chose a **market stop** (Binance STOP_LOSS), chosen for capital preservation and backtest consistency, not profit; trigger levels unchanged; stop-limit fallback printed on the card. Full record: Appendix B.
- **Sharia status:** BTC approved; ETH/SOL/ADA lean "probably" (not final), LTC unaddressed; all pending. Approval alone enables nothing: an approved symbol must also be added to `config/halal_universe.yaml`, and only after a research phase the user starts. Notes: Appendix A. A shared $300 account splits the same risk budget across positions; the universe study found no gain from doing so.
- **Autostart:** ON (2026-10-02). Turn off with `uv run spot autostart off`; cheat sheet in guide section 2.
- **Benner cycle (raised by the user, not started):** low prior (a 1875 chart for 19th-century US farm and iron prices; BTC has about one cycle of history; any hand-picked cycle length overfits). The only sound version would be pre-registered (fix the published year classes in advance, permutation test of BTC returns by class); anything short of a large, stable effect is no evidence. Awaiting the user's approval.

---

## 14. Pre-registration and freeze register

Criteria were written and hashed (SHA-256) **before** results existed. `tests/test_freeze.py` checks every `reports/*freeze*.json`; any change to a hashed file fails the test unless a new freeze record explains why. These files must not be edited or moved.

| Study | Pre-registration (in `reports/`) | Freeze record | Frozen at (UTC) |
|---|---|---|---|
| Challengers | `challenger_preregistration_2026-10-02.md` | `challenger_freeze_2026-10-02.json` | 2026-10-02 08:10 |
| Higher risk | `risk_modes_preregistration_2026-10-02.md` | `risk_modes_freeze_2026-10-02.json` | 08:27 |
| Intraday | `intraday_preregistration_2026-10-02.md` (+ `..._amendment_1_...md`) | `intraday_freeze_2026-10-02.json` | 08:37 |
| Execution | `limit_entry_preregistration_2026-10-02.md` | `limit_entry_freeze_2026-10-02.json` | 09:21 |

Frozen live-strategy files (in every freeze record): `config/rules.yaml`, `spot_trd/regime.py`, `strategy.py`, `sizing.py`, `risk.py` (and `indicators.py`, `config/halal_universe.yaml` in the first two). The sell-order wording change touched only card, dashboard, alert and review text (`run.py`, `dashboard.py`, `watch.py`, `review.py`), none of which are hashed.

---

## 15. Corrections and mistakes log

1. **Equal-drawdown claim** ("a 10-14% BTC holding matches v2, so complexity adds nothing") used a cost-free daily-rebalanced fraction. Corrected by the challenger study (5.5, 7).
2. **Hourly stop check** first measured the hour's open and was always 0% by construction; fixed to measure the in-hour drop.
3. **Research candidate mislabelled** as "v1" when it was v2 (`research.py` copies the live rules); relabelled, and a genuine v1 added to the walk-forward.
4. **"Harsh" per-capital table** briefly pointed at the new gap-stress row after a list edit; caught from the output and fixed.
5. **Day-number bug** in the intraday simulator (nanosecond assumption broke under pandas 3, one entry total instead of one per day); caught by a unit test before any real run.
6. **Intraday leak check** ill-posed for mean reversion; first replacement had no power (0/4); redesigned and documented in the amendment.
7. **Milestone report** wrongly said the historical path "spent most of the first years at or below the start"; the table showed it never fell below $300. Fixed, and a median that mixed time horizons made consistent.
8. **No-rebalance test** assumed constant cash at every entry (test bug); fixed in the test and in the report's verification step.
9. A `usd()` helper was shadowed by a loop variable; fixed.

---

## 16. Everything rejected or not supported

| Idea | Evidence | Where |
|---|---|---|
| v1 fixed targets and 10-day hold | ~no edge | 4.1 |
| Wide trails (4-5 ATR) | best in sample (+82-125%), negative/poor 2023+ | 4.2 |
| Fear & Greed filters (>= 75 block, <= 50 entry), MVRV >= 3, Donchian exit/ensemble | failed the both-periods rule | 4.5 |
| Laya | AUC 0.497, at chance | 4.4 |
| Switching to the best ablation row (1M-only gate) | in-sample pick among 16 | 5.4 |
| Tuning the S&P gate lookback | 100-day cuts edge-test return +57% to +7% | 5.4 |
| Adding ETH/SOL/ADA/LTC (or more positions) | no gain; worse drawdown for BTC+ETH; $25 cannot hold two positions | 6 |
| 200-day trend or core + tactical as replacement | all REJECT, Calmar below v2's | 7 |
| Raising risk per trade to hit a dollar target | 0-24% chance to reach +16.7% in 6 months, ~41% below start, needs ~9% risk/trade | 8 |
| Intraday spot strategies at retail fees | all three lose after ~0.31% costs | 9 |
| Market entry or single limit instead of the ladder | lower Calmar and mean R per signal | 12 |
| Manual limit buy before a v2 plan | changes the signal | 12 |
| Adding capital because growth is slow | +$100 adds ~$3/yr | 11 |
| Treating 2023+ as a clean holdout | contaminated | 2 |
| Treating the FOMC/CPI block as validated | never backtested | 5.1 |
| Leverage, margin, futures, options, short selling, Earn/staking/lending, grid/martingale bots, auto-trading with withdrawal-capable keys | halal constraints / capital preservation | 2 |

---

## 17. Limits of the evidence, and what would change the conclusions

- One BTC price path (2018-2026); about 50 trades; three trades make most of the profit; about 30 variants judged on the same history.
- 2023+ is contaminated; true out-of-sample evidence is only the paper trading from 2026-10-02 (about 6 trades a year).
- Fill models are assumptions; the stop-slippage sensitivity is large (5.2).
- The simulations ignore circuit-breaker pauses and resample past trades (no regime change).
- **Would change the conclusions:** forward paper results (a year shows only gross breakage; expectancy needs ~19 years); much more capital (thousands of dollars produce meaningful dollars at the same risk); a genuinely different edge source tested under pre-registered gates with realistic costs.

---

## 18. Reproduce: commands to archived reports

Detailed generated reports for every section are in `reports/archive/` (snapshot of 2026-10-02). Re-running writes fresh dated files into `reports/`.

| Section | Command | Archived detail |
|---|---|---|
| 4.2 | `uv run spot research` | `research_2026-10-01/02.md` |
| 4.3 | `uv run spot backtest` | `backtest_2026-10-01/02.md` |
| 4.4 | `uv run spot laya-eval` | `laya_eval_2026-10-01.md` |
| 4.5 | `uv run spot upgrades` | `upgrades_2026-10-02.md` |
| 4.6 | `uv run spot validate`, `review`, `decisions` | `validation_2026-10-01.md`, `decisions_paper_2026-10-02.md` |
| 5 | `uv run spot audit` | `audit_2026-10-02.md`, `v3_decision_report_2026-10-02.md`, `final_decision_report_2026-10-02.md` |
| 6 | `uv run spot universe` | `universe_2026-10-02.md`, `sharia_screening_2026-10-02.md` |
| 7 | `uv run python -m spot_trd.challengers` | `challengers_2026-10-02.md` |
| 8 | `uv run python -m spot_trd.risk_modes` | `risk_modes_2026-10-02.md` |
| 9 | `uv run python -m spot_trd.intraday` | `intraday_2026-10-02.md`, `intraday_2026-10-02_run1_as_first_produced.md` |
| 10 | `uv run python -m spot_trd.milestone`; tracker `uv run spot growth` | `milestone_350_2026-10-02.md` |
| 11 | `uv run spot capital` | `capital_efficiency_2026-10-02.md` |
| 12 | `uv run spot limit-entry` | `limit_entry_2026-10-02.md` |
| 13 | n/a | `decision_sell_order_type_2026-10-02.md` |

Tests: `uv run pytest -q` (114 tests: risk caps, halal guard, fills, portfolio engine, journal, card, validation, monitor, dashboard, decision log, freeze, Sharia record, challengers and intraday look-ahead checks, growth tracker, capital simulator).

---

# Appendix A: Sharia screening notes for the research universe (2026-10-02)

**Purpose:** document what each candidate is and where the concerns are, so that *you* can make the religious judgment.
I am not issuing a ruling on any asset. Nothing here changes what the system trades: only BTC is enabled. The other four
are "pending" in `config/sharia_screen.yaml` and are used for research only. The universe test treats eligibility as a
filter that comes first; no asset was chosen because of its backtest.

## 1. How reliable are the sources?

- **Primary-style source used:** the Shariyah Review Bureau (SRB) paper *The Shariah factor in Cryptocurrencies and Tokens*
  (2018), [PDF](https://shariyah.net/wp-content/uploads/2021/05/The-Shariah-factor-in-Cryptocurrencies-and-Tokens.pdf).
  I read it in full. It is a methodology paper, not a fatwa ("by no means a definitive conclusion or fatwa", its own words),
  and it dates from 2018.
- **Everything else I found is secondary:** commercial "is X halal?" sites (Sharlife, CoinStudy, Crypto Ummah, Halal Wallet,
  Zakat Invest and similar) with uneven methods, no named scholars on many pages, and obvious commercial incentives. They
  disagree with each other (for example, Solana is "halal" on one and "doubtful" on another). I used them only to show that
  disagreement exists, never as a deciding source.
- Claims I could **not** verify, so treat them as unconfirmed: that Mufti Taqi Usmani has ruled crypto impermissible (one
  search summary said so; the article it came from did not name him); a news item saying the SRB certified XRP specifically
  (the SRB paper itself contains no per-coin certificates); a 2019 "Ethereum is halal" scholars' paper reported by news sites
  (I did not locate the document).
- General positions reported by a survey article (also uncited to primary texts): permissive (Mufti Faraz Adam, Southeast Asian
  fatwa councils), conditional (AAOIFI is described as still developing standards), prohibitive (Egypt's Grand Mufti, Turkey's
  Diyanet, some Hanafi scholars, mainly citing gharar, speculation and lack of intrinsic value).

## 2. The methodology applied (SRB, plus the usual prohibitions)

From the SRB paper, as I read it:

- Coins that act as peer-to-peer money (it names Bitcoin, **Litecoin**, Ripple) are treated as currency through custom
  (`'urf`): wide acceptance for Bitcoin, "exclusive custom" within their own network for the others.
- Utility and work tokens are rights (`huquq 'urfiyyah`) that may be traded on a secondary market "**provided that the project
  is Shariah compliant** and has passed the Shariah screening".
- Its conclusion: invest only in tokens that passed a screening of the project's core business activity and what the token
  represents.

Operational checklist (C1-C8 in `config/sharia_screen.yaml`): spot ownership only, no yield mechanism in the token, genuine
utility, permissible core business, ecosystem flagged rather than ignored, no issuer return promises, not a meme, held in your
own spot balance with no Earn products.

The contested point is C5 for smart-contract platforms. SRB's "provided that the project is Shariah compliant" is easy to
satisfy for a payment coin and hard to settle for a platform that anyone can build on. Scholars differ on whether holding the
platform's gas token is judged by the token's own function or by what gets built on top.

## 3. Candidates

TVL figures below are from [DefiLlama](https://api.llama.fi/protocols) on 2026-10-02 (saved in
`data/raw/defillama_tvl_by_category.json`). They are a crude proxy: TVL double counts some staking and bridging, and it
measures money parked in apps, not users or fees. "Non-exchange" excludes the CEX-reserve category.

| | BTC | ETH | SOL | ADA | LTC |
|---|---|---|---|---|---|
| Non-exchange TVL | $35.4B | $171.9B | $17.7B | $0.08B | $0.01B |
| Lending-type share (lending, CDP, leveraged farming) | 0.1% | 23.5% | 16.8% | 30.5% | 0% |
| Derivatives-type share | 0% | 3.9% | 6.8% | 2.3% | 0% |
| Staking-type share | 13.4% | 41.0% | 48.5% | 1.0% | 0% |

### BTC (already in your universe)
- **What it is:** proof-of-work payment and store-of-value network; no issuer; no smart-contract ecosystem at the base layer.
- **Utility:** medium of exchange / value storage (SRB's "currency coin" category).
- **Ecosystem:** the large "TVL" is mostly bridged or wrapped BTC used elsewhere, not protocol activity.
- **Concerns:** none specific to the coin beyond the general disagreement about crypto as money (section 4).
- **Flag:** low.

### ETH
- **What it is:** general smart-contract platform. ETH pays transaction fees (gas) and is staking collateral.
- **Utility:** real and necessary (gas).
- **Ecosystem:** interest-based lending and borrowing is about a quarter of non-exchange TVL, plus stablecoin CDPs, derivatives and
  basis trading; also gambling, NFT and meme-token activity (not measured here).
- **Concerns:** the platform proviso (C5). Holding ETH spot is not lending; but part of ETH's value reflects demand from those uses.
  Staking is a separate question and the system never stakes.
- **Disagreement:** secondary sources mostly call spot ETH permissible; some separate the token from the apps, others do not.
- **Flag:** medium. Needs your decision.

### SOL
- **What it is:** high-throughput smart-contract platform (proof of stake plus a time-ordering mechanism called proof of history).
- **Utility:** real (fees, staking).
- **Ecosystem:** lending about 17% and derivatives about 7% of non-exchange TVL; Solana has also been the main venue for
  meme-token launches (not quantified here). Known history of large early insider and exchange-affiliated holdings (a
  centralisation/gharar point some reviewers raise).
- **Disagreement:** aggregator verdicts split between "halal", "neutral" and "doubtful".
- **Flag:** medium to high. Needs your decision.

### ADA
- **What it is:** proof-of-stake smart-contract platform; smart contracts arrived in 2021.
- **Utility:** real but modest (fees, staking, governance).
- **Ecosystem:** tiny: $0.08B non-exchange TVL, of which lending-type is about 30% of a very small base.
- **Disagreement:** aggregators mostly call it permissible; same platform proviso as ETH.
- **Flag:** low to medium. Needs your decision.

### LTC
- **What it is:** proof-of-work payment coin forked from Bitcoin; no smart-contract ecosystem.
- **Utility:** payments; SRB names Litecoin explicitly among currency coins, noting it is not accepted by large merchants but
  functions as medium of exchange inside its own network.
- **Ecosystem:** essentially no DeFi.
- **Concerns:** limited real adoption (gharar/speculation argument applies as it does to any coin); an optional
  confidential-transaction extension (MWEB), which some reviewers dislike for illicit-use risk.
- **Flag:** low. Needs your decision.

### Why LTC is the fifth slot
You asked for one more established non-meme asset. I chose LTC **before running the portfolio test**, on screening grounds
only: oldest of the non-platform coins, a currency coin in SRB's own list, no DeFi or meme ecosystem. For transparency: I had
already run a one-off exploratory pass of eight liquid pairs on the unmodified strategy to see whether the rules behave
differently outside BTC (ETH, BNB, XRP, ADA, LTC, LINK, DOGE, SOL). That table is not used anywhere in the decision, and LTC
turned out to be one of the weakest performers in it, which is some evidence the choice was not performance-driven.

Alternatives I considered and **did not test**, with the reason you may care:
- **XRP:** payments coin controlled by a company with large escrowed supply; centralisation and regulatory history. SRB lists
  "Ripple" as a currency coin, but I could not verify any per-coin certificate.
- **LINK:** oracle token whose main customers are DeFi protocols including lending: strong C5 concern.
- **BNB:** exchange token tied to Binance, which itself offers interest-bearing Earn products, and BNB Chain hosts DeFi lending:
  strong C2/C5 concern for an interest-free policy.
- **DOGE and other meme coins:** excluded by C7.

## 4. Scholarly disagreement in one paragraph

Whether crypto is *mal* (property) and usable as money is itself disputed. Permissive views rely on custom and utility (the SRB
approach). Prohibitive views cite gharar, speculation, lack of backing or intrinsic value, and use in illicit finance. Even among
permitters, staking rewards and DeFi yield are treated differently from spot ownership. If you follow a school or scholar who
rejects crypto as an asset class, every row above is "rejected" and the answer for the system is to hold USDT only.

## 5. What I need from you

For each of ETH, SOL, ADA, LTC, set `user_decision` in `config/sharia_screen.yaml` to `approved`, `rejected`, or leave `pending`.
If you add the criteria you want enforced (for example "exclude any platform where lending-type activity exceeds X% of its
ecosystem"), I will encode them in that file. Separately, an approved symbol must also be added to `allowed_symbols` in
`config/halal_universe.yaml`; the test suite fails if a tradable symbol lacks an approved record.

---

# Appendix B: Decision record, sell-order type on the live card (2026-10-02)

**Decision:** the card now tells you to place the protective sell as a **market stop** (Binance order type `STOP_LOSS`, shown in the app as
"Stop Market") instead of a stop-limit. If your Binance screen does not offer a market stop for BTC/USDT spot, the card prints the old
stop-limit prices as a fallback (trigger and a limit 0.5% below).

**Who decided:** you asked me to choose ("you can choose it yourself"). I chose on your stated priority, **protecting the capital**, and on
consistency with the backtest. I did **not** choose it to increase profit, and I cannot promise it does; the effect on profit is small and
not measurable from history.

## Why

- A stop-limit sell can fail to execute. The hourly check on the 48 historical stop-outs (`audit_2026-10-02.md`): inside the first hour price
  traded through the stop, the hour's low was a median 0.49% below it; in 23 of 48 cases price fell more than the 0.5% limit band within
  that single hour, and in 2 the hour closed below the limit price. In those cases a stop-limit could sit unfilled while price keeps falling.
- A market stop always exits. On an order of about $50 the slippage cost is small, and the backtest already assumes market-like exits
  (0.1% stop slippage in the base case, 0.5% in the harsh case). So a market stop matches the modelled behaviour better than a stop-limit does.
- The audit showed the edge is very sensitive to stop fills: if stops fill 1.5% worse than planned, the edge-test return falls from +57% to +14%.
  Avoiding unfilled stops matters more than saving a few hundredths of a percent.

## What did NOT change

The stop trigger levels, the trailing rule, the entry plan, the signal, the risk sizing, the circuit breakers and every file hashed in the
freeze records. Only the wording of how to place the protective order changed (`run.py`, `dashboard.py`, `watch.py`, `review.py`). The change
was made on 2026-10-02 before any paper trade existed, so forward results are not affected in kind.

## Caveats

- A market stop can fill below the trigger in a fast drop (that is the slippage the backtest assumes). It gives certainty of exit, not of price.
- I cannot see your Binance app. Check that a "Stop Market" option exists for BTC/USDT spot; otherwise use the fallback printed on the card.
- If you disagree, reverting is a text change in `spot_trd/run.py` (`stop_limit`) plus the dashboard and alert strings; the trigger levels never changed.
