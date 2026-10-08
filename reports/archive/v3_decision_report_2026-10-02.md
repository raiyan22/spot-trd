# v3 decision report: is spot-trd economically viable?

Date 2026-10-02. Evidence: `audit_2026-10-02.md`, `universe_2026-10-02.md`, `sharia_screening_2026-10-02.md`. No strategy rule was changed.
All dollar figures are USDT. "Edge test" means 100,000 USDT at 2% risk, which removes Binance's 5 USDT minimum order from the picture.

## Short version

The strategy is **economically weak at $25** and probably at any size you could fund soon. It makes about **$1 a year** on $25
(range $0.60 to $1.70 depending on assumptions), not $10-20. Its edge is real-looking but statistically thin, and a plain
"hold 10% of the account in BTC" rule matched it. Adding ETH, SOL, ADA or LTC did **not** materially improve it. I would not
build more machinery on this until you decide what you want the $25 to do.

## What I fixed before judging (methodology)

| Check | Result |
|---|---|
| Look-ahead / leakage | **None found.** Every feature and signal rebuilt from data truncated at 85 dates matched the full-data values. Macro data timing is safe (S&P/DXY/gold/oil close before the BTC daily close). |
| Data integrity | Clean: no gaps, duplicates or bad prices in 3,333 BTC bars. Oil's negative print (Apr 2020) is clipped. |
| Regime exit | **Was optimistic**: sold at the same close that revealed the signal, with no slippage. Now fills at the next open with 0.1% slippage. |
| Limit buys | **Was optimistic**: touching the limit counted as a fill. Now price must trade 0.05% through it. |
| Costs | Fees and slippage are now tracked per trade (previously only applied). Fee 0.1% per side, no BNB discount assumed. |
| Position sizing | Correct: every stop-out loses exactly -1.00R in the base case, within the 2% / 1% budget. |
| Stop-limit realism | The weak point. Hourly candles on the 48 stop-out days: median in-hour drop below the stop 0.49%; 23 of 48 dropped more than the 0.5% limit band within one hour, and 2 closed below the limit. A stop-limit can fail to fill in fast drops. |
| Not fixable | Selection bias (BTC was picked in hindsight; about 30 rule variants were judged on this one history) and a contaminated "out-of-sample": v2's design came after seeing v1 fail on the full history. |
| Live vs backtest gap | The FOMC/CPI entry block exists only in the live card. It has never been backtested. |

The engine fixes cost little (edge return +58.4% to +57.1%). Stop slippage costs much more.

## A. Does the current strategy have a genuine edge?

**Weak, unproven positive edge. Not a demonstrated one.**

- 50 trades over 8.5 years: win rate 42%, average +0.65R, profit factor 2.1, max drawdown -12.3% (edge test, base fills).
- **Three trades make 78% of the total profit.** Without them the other 47 trades average +0.15R, which is roughly zero after costs.
- Bootstrap 95% interval for average R: [+0.02, +1.38] in the full period, [-0.35, +1.54] in 2023-onward. Because about 30 variants were judged on the same history, the nominal p of 2% is not credible (a crude correction puts it near 60%).
- Walk-forward (each January, choose the best of 21 variants from earlier data only): +13.6% over 2021-2026 (2.2% a year). Three different variants were chosen across the six years, so the selection is unstable.
- Placebo test: random entry days inside the same gate earn a median +33.7% against the real +57%. The pullback timing beats 83% of random runs on return and 100% on average R, so it adds something. But most of the profit comes from the trend gate and the trailing exit, not the entry.
- Parameter neighbours: 27 of 28 one-step changes stay profitable (not a knife-edge), but results range from +7% to +75%. The S&P gate lookback is fragile (100-day instead of 50-day: +57% becomes +7%).
- Other coins with the same untuned rules (a quick exploratory pass, not used for decisions): average R was +0.64 ETH, +0.07 LTC, +0.02 SOL, -0.16 ADA. BTC is the best-looking asset, which suggests the BTC result is partly flattered. Expect the live edge to be smaller than shown.

Trend-following on BTC has a plausible real basis. This implementation's evidence for it is thin, and the true expectancy is more likely near half the backtest than above it.

## B. How much does it realistically make after costs?

| Fills | $25 final (8.5 yrs) | $25 profit/yr | $300 profit/yr | Edge-test return |
|---|---|---|---|---|
| Published v2 (optimistic) | 33.94 | +$1.04 | n/a | +58.4% |
| **Base (now the default)** | 33.74 | **+$1.02** | +$8.89 | +57.1% |
| Harsh (0.5% stop slip) | 30.06 | +$0.59 | +$7.10 | +46.1% |
| Gap stress (stops fill 1.5% worse than sized) | 20.99 | -$0.47 | +$4.13 | +14.0% |

Out-of-sample 2023-onward only: $25 earns about $1.67 a year, $300 about $7.13 a year.
Trades: about 5 a year. Fees about $0.09 a year at $25. The account is in a position 11% of the time and has no trade event on 97% of days.
Average capital in use is only about 4% ($25) or 2% ($300), because 1-2% risk per trade with a ~7% stop means small positions.

Monte Carlo on the observed trades ($25 account, trade-level, small sample so shape not forecast):

| Scenario | 1 year: ending capital 5th / median / 95th | P(end below start) | 3 years: median | 3 years: P(drawdown at least 10%) |
|---|---|---|---|---|
| As observed | $23.37 / $25.09 / $30.88 | 48% | $27.17 | 18% |
| Edge halved | $22.79 / $24.67 / $30.19 | 57% | $25.65 | 44% |
| No edge at all | $22.18 / $24.33 / $29.53 | 63% | $24.22 | 68% |

In any single year the $25 account is about as likely to finish below where it started as above it.

## C. Is $25 economically meaningful?

**No.** $25 produces roughly **$0.60 to $1.70 a year**, about $0.05 to $0.14 a month. The median month is exactly $0. The capital
is not the only limit: the risk rule (2% of $25 = $0.50 per trade) caps what any single trade can earn, and 47 of 101 setups
couldn't even be traded because the position fell under Binance's minimum order.

## D. What starting capital would be meaningful?

| Target | Capital needed at 1% risk (full-period / out-of-sample / halved edge) | At a flat 2% risk |
|---|---|---|
| $1 a day ($365/yr) | $13.6k / $18.4k / $27.3k | about $6.8k |
| $0.10 a day ($36/yr) | $1.4k / $1.8k / $2.7k | about $0.7k |

At $300 the strategy makes about $9 a year at 1% risk, or about $20 a year at 2% risk (max drawdown about 12%).
Those are the honest numbers: roughly 3 to 5% a year on the account, with a 6 to 12% drawdown.

There is a risk-appetite lever that dominates everything else. The simple baseline "hold BTC only while above its 200-day
average, otherwise USDT", with a fraction of the account allocated (no leverage), over the same 8.5 years:

| BTC share of account | Return | Max drawdown | $25 becomes | $300 becomes |
|---|---|---|---|---|
| 10% | +36.8% | -8.9% | $34 | $410 |
| 25% | +112.6% | -21.2% | $53 | $638 |
| 50% | +310.5% | -38.8% | $103 | $1,231 |
| 100% | +1047% | -64.7% | $287 | $3,442 |

This is BTC's 2018-2026 path (it rose about 7x), not a forecast. It shows that returns come from how much BTC risk you carry,
and your "can't lose the $25" rule sits at the low-risk end of this table. That trade-off is yours to set. I will not move it.

## Does the complexity add value?

Compared at the same maximum drawdown (about -12%), no:

| Approach | Total return, 2018-2026 | Max drawdown |
|---|---|---|
| Current strategy, $25 account | +35.0% | -12.3% |
| Current strategy, edge test | +57.1% | -12.3% |
| Hold ~11% of the account in BTC | +44.9% | -12.3% |
| 200-day trend rule at ~14% exposure | +54.4% | -12.3% |

At $25 the strategy (+35%) is below both simple alternatives. On the edge test it is level with the 200-day rule.
Compared as raw all-in strategies, buy-and-hold turned $25 into $184 (-77% max drawdown) and the 200-day rule into $287 (-65%):
far more money, and a drawdown that breaks your capital-preservation rule.

The strategy does have one real property: it sat out 2018 and 2022 entirely (BTC -68% and -64%) and lost nothing in them.
A fixed 11% BTC allocation would have lost about 7% in each of those years.

> **Correction (added later on 2026-10-02, after the pre-registered challenger study).** The equal-drawdown table above
> held a *daily-rebalanced* fraction of the account in BTC, which is cost-free and implicitly sells winners. Implemented as
> something you could actually follow (buy once, no rebalancing), the exposure that matches v2's -12.3% drawdown is only
> 3-4%, and it returns +17-20% against v2's +57% (Calmar 0.15-0.17 against 0.44). So "complexity adds nothing" was **too
> strong**: at equal drawdown, v2 beat unrebalanced passive alternatives in this history. What still holds: v2's return per
> unit of drawdown (Calmar 0.43) is about the same as the all-in 200-day rule's (0.41), so the real difference is how much
> risk you carry, not which rule. See `challengers_2026-10-02.md`.

## E. Does expanding beyond BTC improve the economics?

**No eligible universe passes the test I fixed before running.** The test required, against BTC alone on the same window:
at least 1.5x the trades per year, at least 1.25x the annualized return (and still positive under harsh fills), a max drawdown
no more than 25% deeper, a losing streak no more than 2 trades longer, and no worse return in both halves.

Same v2 rules on every asset, one shared account, total portfolio risk held at the single-asset budget (each slot gets
1/k of it), window 2021-02 to 2026-10 (limited by SOL's history):

| Universe, max positions | Trades/yr | Annualized return | Max drawdown | Edge-test avg R |
|---|---|---|---|---|
| BTC alone (reference) | 6.3 | +2.5% | -12.7% | +0.35 |
| BTC+ETH, 1 | 7.9 | +1.8% | -17.5% | +0.15 |
| BTC+ETH, 2 | 12.0 | +1.3% | -11.5% | +0.25 |
| BTC+ETH+SOL, 3 | 13.6 | +2.5% | -8.0% | +0.33 |
| BTC+ETH+SOL+ADA, 2 | 14.5 | +2.7% | -11.3% | +0.19 |
| 5 assets (adds LTC), 2 | 15.6 | +2.7% | -9.4% | +0.19 |

Adding assets roughly doubles the number of trades, but the annualized return stays near +2.5% in the best cases and falls in
others. The one pattern worth noting is that BTC+ETH+SOL with 3 slots had the same return with a smaller drawdown (-8.0%
vs -12.7%). That is diversification lowering risk, not raising return, it is a single path, and it fails the return test.
In dollars at $300, BTC alone made about $3.5 a year and the best multi-asset case about $4.2, a difference of $0.70 a year.

Two practical blockers: at **$25 a second position is untradable** (1% per slot is $0.25 of risk, under the minimum order), and
SOL has only 5.6 years of data and an average R near zero (+0.02) when run alone.

**Answer to your question:** the smallest eligible universe that materially improves opportunity and expected dollar return
without worsening risk is **none: BTC alone**. BTC+ETH alone is worse than BTC alone on drawdown. BTC alone is still
economically weak, and I would not force more trades to disguise that.

Sharia screening: I documented ETH, SOL, ADA and LTC but made no rulings (`sharia_screening_2026-10-02.md`). Only BTC is enabled.
The sources are mostly commercial aggregators that disagree; the one primary methodology paper (SRB, 2018) says utility tokens
are tradable "provided that the project is Shariah compliant", which is exactly the part you must judge for platform tokens. The
quantified ecosystem facts: lending-type protocols are about 24% of non-exchange DeFi value on Ethereum and 17% on Solana.

## F. Which changes are supported by the evidence?

1. **Keep the conservative fill model** (done). Use the harsh column as your planning number.
2. **Reset expectations** (done in `guide.md`): about $1 a year at $25.
3. **Keep BTC-only and the circuit breakers.** Breakers on gives +57% against +49% off, with a shallower drawdown.
4. **Use a market stop-loss, or at least a wider stop-limit band, for the sell side** (not yet implemented). The hourly evidence says
   a 0.5% limit band can be pierced inside one hour, and a tiny position has no real slippage cost. This is the single execution
   change the data supports. It is a live-card change, so I have left it for your decision.
5. **Treat the FOMC/CPI block as unvalidated.** Either backtest it with historical dates or accept it as a judgment call.

## G. What should NOT be implemented

- Any of the previously rejected ideas (v1 targets, 4-5 ATR trails, Fear & Greed and MVRV filters, Donchian exits, Laya).
- Switching to the best row of the component ablation (for example a 1M-only gate). It looks better only because it was chosen
  after seeing 16 combinations on the same data.
- Tuning the S&P lookback or any threshold to lift the numbers.
- More assets, or more positions, on this evidence. Not at $25, and not at $300.
- Raising risk per trade to chase a daily dollar target. $1 a day needs $7k to $27k of capital at this strategy's returns, or
  a BTC exposure that breaks your loss limit.
- Describing 2023-onward as clean out-of-sample evidence. It is not.

## What I recommend you decide next

1. **Purpose.** If the goal is learning and keeping the $25 safe, the current system is acceptable as a paper-trading tool and
   costs almost nothing. Do not expect income.
2. **Capital.** If you want absolute dollars, the lever is more capital, or more BTC exposure within a drawdown you accept.
3. **Redesign worth testing (only with your go-ahead):** a "core + trend" design that holds a fixed fraction of the account in BTC
   under a simple 200-day rule, as in the table in section D. It is simpler than the current system and matched it at equal drawdown.
   It must be tested on its own with the same rules: fixed in advance, judged out of sample, with realistic fills.
4. **Sharia decisions** for ETH, SOL, ADA, LTC in `config/sharia_screen.yaml`, if you want them researched further.
5. **Live evidence.** Paper trading is the only genuinely untouched data. A year of it, mostly "NO ACTION", is the honest next test.
