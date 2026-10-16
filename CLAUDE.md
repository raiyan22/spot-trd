# spot-trd

Halal BTC/USDT **spot-only** decision-support tool for Binance. It tells the user when to place limit buys, where to put the protective stop, and when to sell; the user places orders manually. The priority is not losing capital, then compounding slowly.

Read first: `guide.md` (how the user runs it), `RESEARCH.md` (everything tested and decided, with a corrections log and a list of rejected ideas: do not re-propose those), `future-improvement.md` (roadmap, ideas awaiting approval). Detailed generated reports: `reports/archive/`.

## Current mode: FORWARD OBSERVATION
- **v2 is frozen and is the experiment.** Do not change strategy rules, parameters, risk, or assets. Do not start new strategy or execution research unless the user explicitly approves it. Slow growth is not a problem to solve; report honestly if forward results show no edge.
- Freeze is enforced: `tests/test_freeze.py` fails if any file hashed in `reports/*freeze*.json` changes (rules.yaml, regime/strategy/sizing/risk code, the pre-registrations). A deliberate change needs a new freeze record that says why.
- **Paper-growth experiment** (started 2026-10-02, `uv run spot growth`): $300, no contributions, target $350 from trading P&L only; milestones $310/320/330/340/350 count REALIZED equity only; risk is not increased at milestones; no real money until a separate decision based on forward evidence. Extra deposits are never profit.
- **LIVE since 2026-10-08 (user's decision): real 25 USDT, `mode live`, journal `journal/trading_journal.csv`.** The $300 paper record is kept but no longer gets cards. The user invests more only if the $25 shows profit, and keeps asking for a profit guarantee: never give one.
- User's capital: $25 actually allocated, $300 maximum committable, possible additions $25-$50 (exceptional, at most $100 in any year, at most yearly). 2030 is a research horizon, not a promise or a deadline.

## Hard constraints
- Spot only: no leverage, margin, futures, options, shorting, Earn/staking/lending (riba). `spot_trd/halal_guard.py` enforces this. Never weaken it.
- Risk per trade 2% of equity under 50 USDT, then 1%. Circuit breakers: 3 losses in a row = 7-day pause; 5% below peak = 30-day pause.
- Decisions use completed **daily** candles only. Live prices are context and alerts, never triggers.
- BTC only. Sharia screening is separate from performance and is the user's decision (`config/sharia_screen.yaml`: only BTC is `approved`; ETH/SOL/ADA carry only a `user_lean` of "probably", not an approval; a test enforces that tradable symbols are approved).
- A manual limit buy before a v2 plan exists is a different strategy: not allowed. When a card says BUY, place the card's own two limit orders. Protective sell = market stop (Binance STOP_LOSS) with a stop-limit fallback printed on the card (decision 2026-10-02, trigger levels unchanged).

## v2 in one paragraph
Buy pullbacks to EMA20 (RSI < 55) only when BTC is above its 10-month SMA, the daily trend is up (close > EMA200, EMA50 > EMA200), and macro is calm (S&P above its 50-day, no DXY surge, no gold+oil spike). Two limit buys at close - 0.25/0.75 ATR (valid 2 days), stop 1 ATR below the lowest, 2-ATR chandelier trailing stop, exit if the 1M/1D trend breaks. FOMC/CPI entry block exists in the live card only (never backtested). Full spec: `RESEARCH.md` section 3.

## Verdict (details and numbers in RESEARCH.md)
Thin, unproven edge: about **$1/yr on $25, $9/yr on $300** (return on capital about 2.7%/yr at any size; three trades made 78% of profit). Tested and not supported: more assets, 200-day trend or core + tactical, higher risk (+16.7% in 6 months reached 0-24% of the time, needs ~9% risk per trade), intraday spot strategies, market entry or a single limit instead of the ladder, extra capital (+$100 adds ~$3/yr). $350 realized: about 5.6 years at the average rate, median ~4.5 years among simulated paths that get there, 80% by year 10, 53% if the edge is half; no honest deadline. Do not oversell the system, force trades, or tune anything to hit a dollar target.

## Process rules for any future research (only when approved)
- Write acceptance criteria **before** testing, hash them in a freeze record, never crown the best-backtest configuration, state pass/fail per gate.
- Use realistic fills (`rules.yaml` `execution`: exits at next open, limit buys need a 0.05% trade-through; harsh and gap-stress scenarios). 2023-onward is contaminated for v2; never call it a clean holdout.
- Disclose mistakes and amendments openly (see RESEARCH.md section 15); keep amendments in separate files rather than editing frozen documents.

## Commands (run from this folder with `uv run spot <cmd>`; `uv run spot` lists all)
- Daily: `today`, `buy --usdt X --btc Y`, `sell --usdt X --btc Y`, `status`, `note "..."`, `cancel`, `skip`
- Monitor: `start` / `stop` / `last [--full]` / `dashboard` / `autostart on|off` / `watch` (all print a terminal summary; missed daily closes are replayed by `spot_trd/catchup.py`)
- Cloud: `.github/workflows/spot.yml` runs `python -m spot_trd.cloud daily|check` (daily records the card's plan/decision and pushes; check is read-only; notifies via GitHub issues, optional ntfy). Replies to an issue/email (`skip`, `bought <usdt> <btc>`, `sold ...`, `cancel`, `note`, `status`) are logged by `.github/workflows/reply.yml` -> `spot_trd/reply.py`. `sync` pulls+pushes the journal and decision logs (union merge); with `cloud_sync: true` spot commands and the monitor sync automatically
- Shadow book: `shadow` (`spot_trd/shadow.py`) replays every journal plan as if placed exactly, vs what the user did; shown on each card. Bookkeeping only, never a reason to change rules
- Evaluation: `growth` (the $300 experiment), `decisions`, `review`, `validate`
- Research: `backtest`, `research`, `upgrades`, `audit`, `universe`, `capital`, `limit-entry`, `laya-eval`, `chart`; and `python -m spot_trd.challengers|risk_modes|intraday|milestone` (intraday needs `data/raw/btc_1h.parquet`)
- Mode: `mode paper|live` (default paper; separate journals)

## Where things live
- Code `spot_trd/` (`cli.py` entry; `run.py` card; `backtest.py` engine with `run_portfolio`/`run_backtest`/`entry_mode`; `strategy.py`, `sizing.py`, `regime.py`, `risk.py`; `watch.py` monitor; `dashboard.py`; `journal.py`; `decisions.py`; `growth.py`; study modules `audit`, `universe`, `challengers`, `risk_modes`, `intraday`, `milestone`, `capital`, `limit_entry`).
- Config `config/` (`rules.yaml` frozen, `events.yaml`, `halal_universe.yaml`, `sharia_screen.yaml`, `watch.yaml`). Journals and logs `journal/`, `logs/` (UTC). Reports `reports/` (frozen pre-registrations and freeze JSONs, `growth_latest.md`, `cards/`, `archive/`).
- Tests `uv run pytest -q` (139; keep them passing).

## Working notes
- Python 3.11 via uv; torch from the cu130 index (RTX 3060 available).
- Windows: the Bash tool wraps commands in single quotes, so heredocs containing `'` break. Use Write/Edit (or a script file) for code.
- Restart the monitor after code changes (`spot stop`, then `spot start --no-open`); it keeps old modules loaded. Autostart is ON.
- The user does not want commit prompts; only touch git if asked.
- To evaluate the system: read `journal/decisions*.csv`, the journal, and run `growth`, `decisions`, `review`, `validate`.
- Open decisions for the user: purpose of the money (practice vs income); whether to test a periodically rebalanced "core BTC + trend" design (needs its own pre-registration); final Sharia approvals; whether to start Benner-cycle or other research.
