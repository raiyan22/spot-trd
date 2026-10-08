# Roadmap and ideas awaiting approval

The project is in **forward observation mode**: v2 is frozen and nothing below starts without the user's explicit approval. What has already been tested, found and rejected is in `RESEARCH.md` (sections 4-12 and 16); do not re-propose those. Priorities follow the goal: **protect the capital, compound slowly, stay halal, keep it simple.** Any strategy change must have its criteria written and frozen before testing and must beat the current rules out of sample, never on backtest gains alone.

## Done
- Always-on monitor: daily card 00:05 UTC, live alerts every 5 minutes on a local HTML dashboard, hidden background process, autostart (ON).
- One-line `>>> TODAY:` decision, live price context, setup trigger, chart; validation layer; execution review; decision log.
- Profitability audit, conservative fill model, small-universe and Sharia study, challenger study, higher-risk study, intraday study, $350 feasibility, capital efficiency, execution comparison (`RESEARCH.md`). This covered earlier roadmap items on Monte Carlo risk reports, overfitting checks and execution realism.
- Paper-growth tracker (`spot growth`), Sharia record with a test that tradable symbols are user-approved, freeze tests for the live strategy and pre-registrations.
- Sell-order decision: market stop with a stop-limit fallback.

## Priority 1: robustness and ease of use (no strategy change)
| # | Improvement | Why | Effort |
|---|---|---|---|
| 1 | **Auto-import fills with a read-only Binance API key** (no trade or withdraw permission) | Manual logging is the main source of errors; it could also reconcile balances and catch a missing stop order. | M |
| 2 | **`spot undo` / `spot fix`** for journal corrections | Editing the CSV by hand is error-prone. | S |
| 3 | **Event calendar auto-update** from the Fed and BLS pages | 2027 CPI dates are not published yet; `validate` warns from early Oct 2026. Add them by hand in `config/events.yaml` until then. | S |
| 4 | **Exchange-limit guard on the card** | Refuse to plan if Binance's minimum order or fees change from the config (today only `validate` checks). | S |
| 5 | **Dashboard additions** | Equity curve, R distribution and the `validate` scorecard on the dashboard; show the growth tracker. | S |
| 6 | **Quarterly re-validation** | Re-run the audit on the newest data; flag if forward results leave the backtest bands. | S |

## Priority 2: scope (only after the live record is solid)
| # | Idea | Note |
|---|---|---|
| 7 | **Zakat report** | Yearly zakat (2.5% of zakatable wealth above nisab) from the journal. |
| 8 | **Stablecoin choice review** | USDT's issuer earns interest on reserves; document a scholar-backed position or alternatives. |
| 9 | **Laya re-test** | Only with genuinely new inputs (for example news), same pre-registered pass/fail rules. |
| 10 | **Volatility-scaled risk** | Only usable above 50 USDT; must pass pre-registered out-of-sample gates. |

## Candidate research awaiting your approval (nothing started)
| Idea | Why it is only a candidate |
|---|---|
| **Periodically rebalanced fixed BTC allocation ("core BTC + trend")** | The challenger study tested buy-once, no-rebalance versions only. A rebalanced design is a different strategy and needs its own pre-registration. It would carry far more drawdown than the 2% risk rule allows. |
| **Benner cycle and crypto returns** | Raised by you. Low prior: an 1875 chart for 19th-century US farm and iron prices, only about one BTC cycle of history, any hand-picked cycle length overfits. The only sound version is a pre-registered permutation test with the published year classes fixed in advance; anything short of a large, stable effect is no evidence. |
| **Extra assets (ETH, SOL, ADA)** | You said you "probably" approve them; recorded as a lean, not an approval. The earlier study found no gain over BTC alone, and a fixed $300 shared across assets only splits the same risk budget. Needs your explicit approval and a research phase. |

## Not planned, by design
Leverage, margin, futures, options, short selling, Earn and staking yield, lending, grid or martingale bots, auto-trading with withdrawal-capable keys, raising risk to hit a dollar target, adding capital merely because growth is slow. These conflict with the halal constraints or with "don't lose the capital".
