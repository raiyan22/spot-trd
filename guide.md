# spot-trd user guide

spot-trd tells you **when to buy BTC, at what price, how much, and when to sell**, using strict halal spot-only rules. You place the orders on Binance yourself. Nothing trades automatically and no API keys are needed.

It does not predict prices. It waits for a pullback inside a confirmed uptrend, risks a small fixed slice of your capital, and lets winners run with a trailing stop. Most days the answer is **NO TRADE**, and that is the system working.

**Current mode: FORWARD OBSERVATION.** The strategy (v2) is frozen and is the experiment: a paper account of $300 growing toward $350 from trading profit only (section 8). What was researched and why is in `RESEARCH.md`; the roadmap is `future-improvement.md`.

Contents: 1 Setup | 2 Monitor (start/stop/autostart, dashboard, alerts) | 3 Daily routine | 4 Reading the card | 5 Weekly checks | 6 What to expect | 7 Paper to live | 8 The $300 to $350 experiment | 9 Analysis commands | 10 Configuration | 11 Troubleshooting | 12 Files

---

## 1. One-time setup

```powershell
cd F:\ryn\spot-trd
uv sync                    # installs everything (uses your RTX 3060 for Laya analysis)
uv run spot                # shows all commands and the current mode
uv run spot deposit 25     # log starting capital (paper mode is the default; the $300 experiment is already set up)
```

**Binance account checklist (halal and safety):**
- [ ] **Simple Earn / Flexible Savings auto-subscribe: OFF.** Otherwise idle USDT can be moved into interest products.
- [ ] No margin, futures or options account enabled.
- [ ] Paying fees with BNB is fine (it's a discount, not interest). If you do, log the fee with `--fee-usdt`.
- [ ] 2FA on, withdrawal whitelist on.

---

## 2. Keep it running for you (always-on monitor)

The monitor is a hidden background program. It writes the daily trade card at **00:05 UTC** and refreshes the dashboard **every 5 minutes**. It only watches and suggests; it never places orders. Stopping it does not change your journal, your paper account or the rules.

### Start, stop and autostart (cheat sheet)

Run in a terminal in `F:\ryn\spot-trd`:

| What you want | Command |
|---|---|
| Is it running? Latest card and recent events | `uv run spot last` |
| Open the dashboard page | `uv run spot dashboard` |
| **Stop the monitor now** | `uv run spot stop` (exits within about 5 seconds) |
| **Start it again now** | `uv run spot start` (add `--no-open` to skip opening the dashboard) |
| **Turn autostart OFF** (stop it starting at login) | `uv run spot autostart off` |
| **Turn autostart ON** | `uv run spot autostart on` |
| Is autostart on or off? | `uv run spot autostart` |
| Run it in a visible window instead (Ctrl+C stops) | `uv run spot watch` |
| Track the $300 to $350 paper experiment | `uv run spot growth` |

- **Autostart is currently ON** (set 2026-10-02): the monitor starts hidden each time you log in to Windows.
- `spot autostart off` only stops it starting at login. A monitor already running keeps going until `spot stop`. To switch everything off: `autostart off`, then `stop`.
- Without the command line you can delete this file to turn autostart off: `C:\Users\USER\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\spot-trd-monitor.vbs` (end the python process in Task Manager to stop it immediately).
- Starting and stopping are always safe. Your orders live on Binance, not in the monitor, and it **catches up** when it runs again (also `spot today`): every daily close it missed is replayed with the same rules, using data up to that close only. The card then shows a "WHILE THE APP WAS OFF" list. A buy plan from a missed day is recorded if its limit orders are still valid (place them then); an expired one is only reported, never chased. For an open trade, the stop and the trend exit are replayed from the entry day, so a break on a missed day still says SELL. You only miss the live alerts while it was off (the cloud runner below covers those).
- The terminal shows the decision too: `spot start`, `spot last`, `spot dashboard` and plain `uv run spot` print a short summary (today's decision, the exact orders, BTC price, equity, alerts, missed days). `spot last --full` prints the whole card.
- **If a buy filled while you were away**, log it with its fill time so it matches the plan that was active then: `spot buy --usdt X --btc Y --time 2026-10-09T03:15:00`.
- It only runs while the PC is on and you are logged in. In Windows Settings > System > Power & sleep, set "When plugged in, PC goes to sleep after" to **Never** if you want it current around the clock; if the PC sleeps nothing breaks.
- Daily cards are saved in `reports/cards/`; the monitor log is `logs/watch.log` (UTC). After any code change, restart it (`stop`, then `start --no-open`), because it keeps old modules loaded.

### Run it in the cloud (GitHub Actions, PC off)
`.github/workflows/spot.yml` runs in a **private** GitHub repo: the daily card at about 00:12 UTC, and every 3 hours the live-price alerts (stop near or hit, limit buy touched, cancel-soon). It is read-only. It never writes your journal and never places orders, and it needs no Binance keys.
- **Notifications:** when there is something to do (not NO ACTION), or an alert fires, it opens a GitHub issue in the repo, which GitHub emails you and pushes to the GitHub mobile app. Each card or alert is sent once. Every run's card is also in the repo's Actions tab. Optional phone push: install the ntfy app, subscribe to a long random topic name, and add it as the repo secret `NTFY_TOPIC`.
- **Keep it informed:** the cloud only knows your trade, stop and plan from the journal you push. `uv run spot sync` pushes it, and with `cloud_sync: true` in `config/watch.yaml` it is pushed automatically after `spot buy/sell/cancel/note`.
- **A buy plan from the cloud:** place the orders from the notification. On your PC, `spot today` (or the monitor) records the same plan through catch-up before you log a fill.
- Cost: free within GitHub's private-repo allowance (about 2000 minutes a month; this uses about 300 to 450). GitHub can start scheduled runs some minutes late.
- The PC monitor and the cloud can both run; they don't conflict.

### The dashboard
`dashboard/index.html` is a local file in your browser (nothing is published). The monitor rewrites it every 5 minutes and the page reloads itself every 2 minutes, so a bookmarked tab stays current. If it stops updating, a red banner says so. From top to bottom:

1. **TODAY:** the decision in one line (No action / Place buy orders / Update your stop / Sell or check now), with exact steps when there is something to do.
2. **Alerts:** anything needing attention right now, or "No alerts".
3. **Tiles:** live BTC price, equity, how far price must move to reach your trigger, stop or limit buy, daily RSI, volatility (ATR).
4. **Daily and 4H charts:** hover for exact prices; EMA20/50/200 lines; past setups; your levels as dashed lines.
5. **Key levels, gates, account and closed trades,** plus the full card text.

Windows pop-ups are off (`desktop_notifications: true` in `config/watch.yaml` turns them on).

### What it checks, and how often
| What | When | Why this interval |
|---|---|---|
| **Daily decision card** (BTC daily candle, macro, events) | **00:05 UTC daily** | The strategy decides on the daily close; 5 minutes after it, Binance's candle and the previous US session's S&P/gold/oil/DXY closes are final. |
| **Live price, alerts, dashboard refresh** | **Every 5 minutes** | Fast enough to warn before anything urgent, slow enough to avoid noise. Your stop order already protects you on Binance; faster checks add temptation, not safety. |
| Macro data (S&P 500, gold, oil, DXY) | Once daily, with the card | These markets close once a day (about 20:00-21:00 UTC). |
| Event calendar (FOMC/CPI) | Once daily, with the card | Dates are fixed in advance. |
| Exchange limits and system health | Weekly via `spot validate` | They rarely change. |

All changeable in `config/watch.yaml`.

### Alerts
| Alert | What to do |
|---|---|
| **BUY may have filled** | Check Binance. If filled, place the market stop shown in the message, then `spot buy ...`. |
| **Price is close to your stop** | Make sure your stop order is live on Binance. Don't move it down. |
| **SELL CHECK: price is below your stop** | Check the stop order executed. If it did not, sell at market, then `spot sell ...`. |
| **Cancel unfilled limit buys soon** | Cancel any unfilled buys when they expire. |
| **Buy setup may form at today's close** | Information only. |
| **Live price unavailable** / **Today's daily card is pending** | Nothing; it retries on its own. |
| Red **NO DECISION: data problem** | Do nothing new until it clears; check your internet connection. |

---

## 3. Daily routine (about 2 minutes)

Each day after 00:05 UTC glance at the dashboard (or `uv run spot last`). Without the monitor run `uv run spot today`. The second line of every card is the decision:

```
>>> TODAY: NO ACTION. Stay in USDT. A buy plan appears if a daily close is <= 82,803 with RSI < 55.
```

| Decision | What you do on Binance | What you log |
|---|---|---|
| **NO TRADE** | Nothing. | Nothing. |
| **BUY** | Place each listed **Limit** buy (Spot > Limit > price and amount as printed). Cancel unfilled orders at the time shown. | After a fill: `uv run spot buy --usdt <Total> --btc <Filled>` |
| *(after a buy fills)* | Immediately place a **Stop Market** sell (Binance STOP_LOSS) for all BTC you hold at the card's *trigger* price. If your app only offers Stop-Limit, use the trigger and limit printed on the card. | Nothing. |
| **HOLD** | Cancel the old stop order and place the new one at the printed trigger. The stop only moves up. | Nothing. |
| **SELL ALL AT MARKET** | Market sell all BTC from this trade. | `uv run spot sell --usdt <Total> --btc <Amount>` |
| **STOP WAS HIT** | Check Order History. If the stop order executed, log it. If it did not, market sell now. | `uv run spot sell ...` |
| **DATA PROBLEM** | Nothing. Rerun later; it refuses to decide on stale data. | Nothing. |

**Numbers to log:** Binance > Orders > Spot Order > **Order History**: use *Filled* (BTC) and *Total* (USDT). If the fee was taken in BTC, log the BTC you actually received. Without logging, the paper account does not move.

**Rules you never break:**
- Only buy what a card tells you to buy. The journal refuses unplanned buys. **No manual limit buy before a card issues a plan**: that would be a different strategy (`RESEARCH.md` section 12).
- Never move a stop **down**, and never skip placing it.
- Never override a circuit-breaker pause.

**Sell-order type (decision 2026-10-02):** protect the position with a **market stop**. A stop-limit can sit unfilled if price falls through its limit (in 23 of 48 historical stop-outs price fell more than the 0.5% band within one hour); a market stop always exits, at the cost of some slippage on a tiny order. Trigger levels did not change. Check that "Stop Market" exists for BTC/USDT spot in your app; otherwise use the fallback on the card. Details: `RESEARCH.md` Appendix B.

---

## 4. Reading the card

```
=== SPOT-TRD CARD for 2026-10-01 (daily close 2026-09-30, rules v2) ===
Account: equity ~300.00 USDT (cash 300.00)
BTC close 83,623.60 | EMA20 81,983 | EMA50 77,807 | EMA200 74,451 | RSI 61 | ATR 2,265 (2.7%)
Gates: 1M uptrend yes | 1D uptrend yes | macro calm yes (...)
DECISION: NO TRADE. Uptrend intact but no pullback setup ...
History (...): BTC 10 days later averaged +2.1%, up 53% of the time, worst 10% -9.6%.
LIVE 84,868.00 at 17:28 UTC ...
  Setup watch: a daily close at or below ~82,803 ... creates a buy plan; that's 2.4% below the live price.
```

| Line | Meaning |
|---|---|
| **Gates** | All three must say *yes* before any buy. **1M uptrend**: price above its 10-month average. **1D uptrend**: price above the 200-day EMA and the 50-day above the 200-day. **Macro calm**: S&P 500 above its 50-day average, no sharp dollar (DXY) surge, no gold+oil stress spike. |
| **EMA20 / RSI** | The entry trigger: a daily close near or below EMA20 (within 1%), still above EMA50, RSI below 55. |
| **ATR** | Typical daily range. Stops and limit prices are set in ATR units, so they adapt to volatility. |
| **History** | What BTC did on past days like today: context, not a forecast. |
| **LIVE** | The current price and how far it is from the levels that matter. Decisions still use the daily close. |
| **Setup watch** | The exact price where a buy plan would appear tomorrow. |
| **Chart** | PNG of daily candles with EMAs, regime shading, past setups, live price and recent 4H candles. |

---

## 5. Weekly, and after every closed trade

```powershell
uv run spot validate   # health scorecard
uv run spot review     # post-mortem of closed trades
uv run spot decisions  # the system's own decisions vs what BTC did next
```

**`validate`** prints PASS / INFO / WARN / FAIL for: data freshness and completeness, price sanity and the event calendar (60 days ahead); Binance's minimum order, lot step and fee vs the config; strategy decay (last 12 months vs long-run); and, once trades have closed, whether your average R, win rate, worst loss (never beyond 1R) and drawdown sit inside the backtest's range. PASS/INFO: carry on. WARN: read it. **FAIL: stop opening new trades until it is understood** and ask Claude to review the journal and the report.

**`decisions`** evaluates the *system's* choices. Every daily decision is logged with its reason and inputs in `journal/decisions_paper.csv` (`decisions.csv` when live), compared with what BTC did 5/10/20 days later: which rule caused missed rallies (stayed out, BTC rose >= 5%) and avoided drops, and how each buy plan turned out. Judge a rule only after dozens of days. To have Claude evaluate and improve the system, ask it to "review the decision log, journal and validation report".

**`review`** shows win rate, expectancy in R, profit factor, drawdown and plan adherence, and flags execution mistakes (*chased entry*, *late stop*, *discretionary exit*, *late regime exit*) with the lesson to apply. Reports go to `reports/` and `journal/reviews/`.

---

## 6. What to expect

From the audited backtest (2018-2026, conservative fills; see `RESEARCH.md` sections 5, 10, 11):

| | Value |
|---|---|
| Trades | About 5-6 per year. Sometimes **zero for many months** (none from Oct 2025 to Aug 2026 while BTC fell 46%). |
| Win rate | About 35-45%. Most trades are small losses or breakeven. |
| Profit source | A few large trend winners (average +0.4 to +0.65R per trade). **Three trades made 78% of the profit.** |
| Max drawdown | About -12% on $25; about -6% (about $19) on $300. |
| Growth | **About 2-4% a year after realistic costs: roughly $0.60-$1.70 a year on $25 and $7-$9 a year on $300.** A capital-preserving practice tool, not income. The sample is small, so the true figure could be lower; being below the starting capital for long stretches is normal. |
| Risk per trade | 2% of equity under 50 USDT, then 1% (Binance's 5 USDT minimum order makes 1% impossible on tiny accounts: 47% of setups at $25 cannot be traded). |
| Another $100 of capital | Adds only about $3 a year. Return on capital is about 2.7% a year at any size. |

A losing streak of 3 to 5 trades is **normal**. Short-term discipline (cutting losers fast at 1R) pays for the long-term profit (letting the few big trends run): of all trades, 40% last 0-7 days (-0.47R), 48% last 8-20 days (+0.44R), 12% last 21+ days (+5.23R, about 96% of profit). The most expensive mistake is taking quick profits early. Compounding is automatic: every trade is sized from current equity.

---

## 7. Paper to live

Switch with `uv run spot mode live`, then `uv run spot deposit <real USDT>`. **Reaching $350 on paper is not a reason to go live.** Going live needs a separate decision based on forward evidence. Minimum checklist:

- [ ] You ran the daily card for at least 2 weeks without missing days.
- [ ] Every paper trade shows **no mistakes** in `spot review`.
- [ ] `spot validate` is PASS or INFO.
- [ ] You have rehearsed placing a limit buy and a stop-market order on Binance.
- [ ] You accept the expected economics in section 6 (about $1 a year on $25).

Paper and live journals are separate files. `spot mode paper` switches back.

---

## 8. The $300 to $350 paper-growth experiment

Started 2026-10-02: paper account, **$300, no contributions**, v2 frozen, risk per trade unchanged at every milestone, trading profit only (any extra deposit would be flagged and never counted). Run `uv run spot growth` any time (read-only): realized vs unrealized equity, milestones **$310/$320/$330/$340/$350 counted on realized equity only**, fees, slippage, win rate, profit factor, R per trade, drawdown, losing streaks, capital utilisation, days spent waiting for a valid setup, and where realized equity would sit by now in the simulations (context, not a deadline). Output is also saved in `reports/growth_latest.md` and `journal/growth_equity.csv`.

How long should $350 take? About 5.6 years at the average profit rate (7 with harsh fills, 11 with half the edge). In simulations the median path that gets there needs about 4.5 years; 80% of base paths get there within 10 years, 53% if the edge is half what history shows. **There is no deadline.** A year of paper results (about 6 trades) can only reveal gross breakage; confirming the edge would take about 19 years at this trade rate.

Capital: $25 is what you have allocated, $300 the maximum; additions of $25-$50 are exceptional, never more than $100 in a year, and the research found no capital level inside these limits turns this into income (`spot capital`, `RESEARCH.md` section 11).

---

## 9. Analysis commands

| Command | When |
|---|---|
| `uv run spot chart` | The live chart without a decision. |
| `uv run spot backtest` | Full-history backtest report. |
| `uv run spot research` / `upgrades` | Compare rule variants walk-forward / re-test literature ideas (only when a new research phase is approved). |
| `uv run spot audit` | Profitability audit (realistic fills, walk-forward, baselines, dollars per capital, Monte Carlo). |
| `uv run spot universe` | Multi-asset study (research only; BTC is the only tradable asset). |
| `uv run spot capital` | Is v2 worth continuing at your capital? Profit per capital level, +$25/$50/$100 a year, 2030 horizon. |
| `uv run spot limit-entry` | Execution comparison for the frozen signals. |
| `uv run python -m spot_trd.challengers` / `risk_modes` / `intraday` / `milestone` | The pre-registered studies. |
| `uv run spot laya-eval` | Only if genuinely new information is added (Laya scored at chance). |

---

## 10. Configuration

| File | Change it? |
|---|---|
| `config/watch.yaml` | Yes, for different alert timing or sensitivity. |
| `config/events.yaml` | **Yes, yearly.** Add next year's FOMC and CPI dates (`validate` warns 60 days ahead; 2027 CPI dates are not published yet). |
| `config/rules.yaml` | **No: frozen** (hashed; `tests/test_freeze.py` fails if it changes). A deliberate change needs a new freeze record that says why. |
| `config/halal_universe.yaml` | Only to add a coin you have approved in `config/sharia_screen.yaml` and after a research phase you start. |
| `config/sharia_screen.yaml` | Your religious decisions: set `user_decision` (approved/pending/rejected). ETH/SOL/ADA currently carry a `user_lean` only. |

---

## 11. Troubleshooting

| Problem | Fix |
|---|---|
| `DATA PROBLEM: no decision today` | Usually a network blip or a run before 00:00 UTC. Rerun in a few minutes. |
| `[WARN] Live price unavailable` | Binance could not be reached; the decision is still valid. |
| `spot start` says it is already running | It is. `spot last` shows status; `spot stop` first to restart it. |
| Dashboard shows a red "not updating" banner | The monitor stopped (restart, or `spot stop`). Run `uv run spot start` or turn on `spot autostart on`. |
| `No capital logged yet` | `uv run spot deposit <amount>` (once per mode; the experiment's deposit already exists). |
| `No open trade or active plan` when logging a buy | The plan expired or never existed. Don't buy without a card. |
| Binance rejects an order "below minimum" | Rerun `spot today`; sizing already keeps orders >= 5.5 USDT, so check you typed the amount exactly. |
| You logged a wrong number | The journal is append-only. Open `journal/paper_journal.csv` (or `trading_journal.csv`), fix the row carefully, then `spot status`. |
| The saved card text shows the wrong equity | It was written before a journal change; the next 00:05 UTC card is correct. |

---

## 12. Files

```
README.md               what this is, and the map of the docs
guide.md                this file (how to run it)
RESEARCH.md             everything that was tested, found and decided
future-improvement.md   roadmap and ideas awaiting approval
CLAUDE.md               briefing for Claude sessions
config/                 rules.yaml (frozen), events.yaml, halal_universe.yaml, sharia_screen.yaml, watch.yaml
journal/                paper_journal.csv, trading_journal.csv, decisions*.csv, growth_experiment.json, growth_equity.csv,
                        archive/ (the old $25 paper journal), reviews/, monitor state
logs/                   watch.log (UTC)
reports/                frozen pre-registrations + freeze records, growth_latest.md, cards/ (daily cards), archive/ (detailed reports)
spot_trd/               the code (cli.py is the entry point)
tests/                  114 tests
```
