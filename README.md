# spot-trd

A halal, **spot-only BTC/USDT** decision-support tool for Binance. It tells you when to place limit buys, where to put the protective stop, and when to sell; you place the orders by hand. No leverage, futures, margin, options, short selling or interest products. No API keys, no auto-trading.

**Status (2026-10-02): forward observation.** The strategy (v2) is frozen and runs as a paper experiment: **$300, no contributions, target $350 from trading profit only.** The research found a thin, unproven edge worth about **$1 a year on $25 and $9 a year on $300**; nothing tested beat it, and $350 is a multi-year outcome with no honest deadline. It is a capital-preserving practice tool, not an income source.

## Quick start
```powershell
cd F:\ryn\spot-trd
uv sync
uv run spot            # all commands
uv run spot growth     # the $300 -> $350 paper experiment (read-only)
uv run spot last       # monitor status and the latest decision card
uv run spot dashboard  # open the live dashboard
```
The monitor runs hidden in the background (paper mode, autostart on) and writes the daily card at 00:05 UTC. To stop or start it: `uv run spot stop` / `uv run spot start`; autostart: `uv run spot autostart off|on`.

## The docs
| File | What it is |
|---|---|
| `guide.md` | How to run it: setup, monitor start/stop/autostart, daily routine, reading the card, weekly checks, what to expect, the paper experiment, troubleshooting. |
| `RESEARCH.md` | Everything that was tested and decided: strategy rules, backtests, the profitability audit, challengers, higher risk, intraday, feasibility of $350, capital efficiency and 2030, execution comparison, Sharia notes, corrections log, rejected ideas. |
| `future-improvement.md` | Roadmap and ideas awaiting your approval. |
| `CLAUDE.md` | Briefing that Claude Code loads automatically in this folder. |
| `reports/` | Frozen pre-registrations and their hash records (checked by the tests), `growth_latest.md`, daily `cards/`, and `archive/` with the detailed generated reports. |

## Where decisions are yours
Risk appetite and the purpose of the money; Sharia approvals (`config/sharia_screen.yaml`); whether to approve any new research phase. Nothing new is researched or changed in v2 without your explicit approval.
