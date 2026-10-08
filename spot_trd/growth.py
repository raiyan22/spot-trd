"""Paper-growth experiment tracker: $300 -> $350 from trading P&L only. Read-only: it never changes v2 or the journal.

Everything is rebuilt from the append-only paper journal plus daily BTC closes, so there is nothing to keep in sync.
Milestones count REALIZED equity only (deposit + closed-trade P&L, fees included). Unrealized gains are shown but never counted.
Run: uv run spot growth            (initialise once with: uv run spot growth --init)
"""
import argparse
import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from spot_trd.config import PAPER_JOURNAL_PATH, REPORTS_DIR, ROOT, load_rules
from spot_trd.journal import append_event, read_events, utcnow

EXPERIMENT_FILE = ROOT / "journal" / "growth_experiment.json"
DECISIONS_PAPER = ROOT / "journal" / "decisions_paper.csv"
EQUITY_CSV = ROOT / "journal" / "growth_equity.csv"
REPORT_FILE = REPORTS_DIR / "growth_latest.md"
START_EQUITY, TARGET_EQUITY = 300.0, 350.0
MILESTONES = (310, 320, 330, 340, 350)
WAITING_REASONS = ("no_pullback", "event_window", "circuit_breaker", "min_order_size")


def _num(v) -> float:
    return float(v) if v not in ("", None) else 0.0


def replay(events: list[dict], cutoff: pd.Timestamp, dust: float):
    """State after every event up to `cutoff`: cash, BTC held, deposits, per-trade cost/proceeds, closed trades."""
    cash = deposits = held = 0.0
    trades: dict[str, dict] = {}
    for e in events:
        when = pd.Timestamp(e["time_utc"])
        if when > cutoff:
            break
        kind, tid = e["event"], e["trade_id"]
        btc, usdt, fee = _num(e["btc"]), _num(e["usdt"]), _num(e["fee_usdt"])
        if kind == "deposit":
            cash += usdt
            deposits += usdt
        elif kind == "plan":
            trades[tid] = {"plan": json.loads(e["details"]), "bought": 0.0, "sold": 0.0, "cost": 0.0, "proceeds": 0.0,
                           "fees": 0.0, "first": None, "closed": None, "cancelled": False, "fills": []}
        elif kind == "buy":
            t = trades[tid]
            t["bought"] += btc
            t["cost"] += usdt + fee
            t["fees"] += fee
            t["first"] = t["first"] or when
            t["fills"].append(("buy", usdt / btc if btc else 0.0, btc))
            cash -= usdt + fee
            held += btc
        elif kind == "sell":
            t = trades[tid]
            t["sold"] += btc
            t["proceeds"] += usdt - fee
            t["fees"] += fee
            t["fills"].append(("sell", usdt / btc if btc else 0.0, btc))
            cash += usdt - fee
            held -= btc
            if t["bought"] - t["sold"] < dust:
                t["closed"] = when
        elif kind == "cancel":
            trades[tid]["cancelled"] = True
    return cash, held, deposits, trades


@dataclass
class Snapshot:
    start_equity: float
    deposits: float
    contributions: float
    cash: float
    held: float
    last_close: float
    last_close_date: pd.Timestamp | None
    marked_equity: float
    realized_equity: float
    realized_pnl: float
    unrealized_pnl: float
    fees_logged: float
    fees_estimated: float
    slippage_buy_measured: float
    slippage_sell_estimated: float
    closed: list[dict]
    open_trade: dict | None
    plans: int
    unfilled_plans: int
    win_rate: float
    profit_factor: float
    avg_R: float
    max_dd: float
    utilization: float
    utilization_in_trade: float
    longest_losing_streak: int
    current_losing_streak: int
    waiting_days: int
    cards: int
    reasons: dict
    days_since_last_trade: int | None
    milestones: dict
    curve: pd.DataFrame
    frozen: bool
    elapsed_days: int
    started: pd.Timestamp


def frozen_ok() -> bool:
    try:
        changed = []
        for path in sorted((REPORTS_DIR).glob("*freeze*.json")):
            for f, d in json.loads(path.read_text(encoding="utf-8"))["sha256"].items():
                if hashlib.sha256((ROOT / f).read_bytes()).hexdigest() != d:
                    changed.append(f)
        return not changed
    except Exception:
        return False


def compute(path=PAPER_JOURNAL_PATH, btc: pd.DataFrame | None = None, decisions_path=DECISIONS_PAPER, now: pd.Timestamp | None = None,
            rules: dict | None = None) -> Snapshot:
    rules = rules or load_rules()
    dust, fee_rate = rules["market"]["qty_step"], rules["market"]["fee_rate"]
    slip = rules["exit"]["stop_slippage"]
    events = read_events(path)
    now = now or utcnow()
    exp = json.loads(EXPERIMENT_FILE.read_text(encoding="utf-8")) if EXPERIMENT_FILE.exists() else {}
    first_dep = next((e for e in events if e["event"] == "deposit"), None)
    if first_dep is None:
        raise SystemExit("No deposit in the paper journal. Start the experiment with: uv run spot growth --init")
    started = pd.Timestamp(exp.get("started_utc", first_dep["time_utc"]))
    start_equity = float(exp.get("start_equity", _num(first_dep["usdt"])))

    cash, held, deposits, trades = replay(events, now, dust)
    contributions = deposits - start_equity
    closed_t = {k: v for k, v in trades.items() if v["closed"] is not None}
    realized_pnl = sum(t["proceeds"] - t["cost"] for t in closed_t.values())
    realized_equity = start_equity + realized_pnl

    closes = btc["close"] if btc is not None else pd.Series(dtype=float)
    last_close_date = closes.index[-1] if len(closes) else None
    last_close = float(closes.iloc[-1]) if len(closes) else float("nan")
    marked = (cash + held * last_close - contributions) if len(closes) else cash - contributions
    unrealized = marked - realized_equity

    # daily curve (marked equity net of any contributions, realized equity)
    rows = []
    if len(closes):
        for d in closes.index[closes.index >= started.normalize()]:
            c_d, h_d, dep_d, tr_d = replay(events, d + pd.Timedelta(hours=23, minutes=59, seconds=59), dust)
            real_d = start_equity + sum(t["proceeds"] - t["cost"] for t in tr_d.values() if t["closed"] is not None)
            mk_d = c_d + h_d * closes.loc[d] - (dep_d - start_equity)
            rows.append({"date": d, "marked": mk_d, "realized": real_d, "btc_value": h_d * closes.loc[d]})
    curve = pd.DataFrame(rows)
    if len(curve):
        eq = pd.concat([pd.Series([start_equity]), curve["marked"]], ignore_index=True)
        max_dd = float((eq / eq.cummax() - 1).min())
        util = float((curve["btc_value"] / curve["marked"]).mean())
        in_trade = curve["btc_value"] > 0
        util_in = float((curve.loc[in_trade, "btc_value"] / curve.loc[in_trade, "marked"]).mean()) if in_trade.any() else 0.0
        curve.to_csv(EQUITY_CSV, index=False)
    else:
        max_dd, util, util_in = 0.0, 0.0, 0.0

    # closed-trade statistics
    closed = []
    for tid, t in sorted(closed_t.items(), key=lambda kv: kv[1]["closed"]):
        risk = t["cost"] - t["bought"] * t["plan"]["stop"] * (1 - slip) * (1 - fee_rate)
        pnl = t["proceeds"] - t["cost"]
        closed.append({"id": tid, "opened": t["first"], "closed": t["closed"], "pnl": pnl, "R": pnl / risk if risk > 0 else 0.0})
    pnls = np.array([c["pnl"] for c in closed])
    wins = pnls > 0
    gains, losses = pnls[wins].sum(), -pnls[~wins].sum()
    streak = best = 0
    for p in pnls:
        streak = streak + 1 if p < 0 else 0
        best = max(best, streak)
    cur_streak = 0
    for p in pnls[::-1]:
        if p < 0:
            cur_streak += 1
        else:
            break
    open_t = next(({"id": k, **v} for k, v in trades.items() if v["first"] and v["closed"] is None), None)
    if open_t:
        open_t["avg_entry"] = open_t["cost"] / open_t["bought"]
    plans = len(trades)
    unfilled = sum(1 for t in trades.values() if t["first"] is None and (t["cancelled"] or pd.Timestamp(t["plan"]["valid_until"]) <= now))

    fees_logged = sum(t["fees"] for t in trades.values())
    notional = sum(t["cost"] for t in trades.values() if t["first"]) + sum(t["proceeds"] for t in trades.values())
    # buy-side slippage: a fill worse than the plan's best matching limit price (limit buys normally fill at or better)
    slip_buy = 0.0
    for t in trades.values():
        prices = [p for p, _ in t["plan"]["orders"]]
        for side, px, qty in t["fills"]:
            if side == "buy" and prices:
                limit = min(prices, key=lambda p: abs(p - px))
                slip_buy += max(px - limit, 0.0) * qty
    slip_sell_est = sum(t["proceeds"] for t in closed_t.values()) * slip

    # decisions: time spent waiting for a valid setup
    reasons, cards, waiting = {}, 0, 0
    if decisions_path.exists():
        dec = pd.read_csv(decisions_path)
        dec = dec[pd.to_datetime(dec["card_day"]) >= started.normalize()]
        cards = len(dec)
        reasons = dec["reason"].str.replace(r"^gate:.*", "gate", regex=True).value_counts().to_dict()
        waiting = int(dec["reason"].str.startswith("gate").sum() + dec["reason"].isin(WAITING_REASONS).sum())
    last_exit = max((c["closed"] for c in closed), default=None)
    since = (now.normalize() - last_exit.normalize()).days if last_exit is not None else None

    ms = {}
    for m in MILESTONES:
        first_date = None
        if len(curve):
            hit = curve[curve["realized"] >= m]
            first_date = hit["date"].iloc[0] if len(hit) else None
        ms[m] = {"reached": first_date, "secured_now": realized_equity >= m, "marked_now": marked >= m}
    return Snapshot(start_equity, deposits, contributions, cash, held, last_close, last_close_date, marked, realized_equity, realized_pnl,
                    unrealized, fees_logged, notional * fee_rate, slip_buy, slip_sell_est, closed, open_t, plans, unfilled,
                    float(wins.mean()) if len(pnls) else float("nan"), float(gains / losses) if losses > 0 else float("nan"),
                    float(np.mean([c["R"] for c in closed])) if closed else float("nan"), max_dd, util, util_in, best, cur_streak,
                    waiting, cards, reasons, since, ms, curve, frozen_ok(), (now - started).days, started)


def context_band(elapsed_years: float) -> str:
    """Where realized equity would sit by now in the base and conservative simulations (context, not a deadline)."""
    from spot_trd.audit import ladder
    from spot_trd.backtest import run_backtest
    from spot_trd.config import load_universe
    from spot_trd.data import load_data
    from spot_trd.milestone import fractions, simulate, state_at
    from spot_trd.regime import build_features

    base, uni = load_rules(), load_universe()
    btc, macro = load_data()
    feat = build_features(btc, macro, base)
    res = run_backtest(feat, ladder(base)[2][1], uni, START_EQUITY)
    fr = fractions(res)
    rate = len(res.trades) / ((feat.index[-1] - feat.index[0]).days / 365.25)
    out = []
    for name, shift in (("base", 0.0), ("conservative (half the edge)", 0.5)):
        T, E = simulate(fr, rate, 10, 10_000, 31, shift)
        t = max(elapsed_years, 1 / 12)
        eq = state_at(T, E, t)
        lo, md, hi = np.percentile(eq, [5, 50, 95])
        out.append(f"{name}: 5th / median / 95th percentile ${lo:.2f} / ${md:.2f} / ${hi:.2f}")
    return "; ".join(out)


def format_report(s: Snapshot, band: str | None = None) -> str:
    f = lambda x: f"{x:+,.2f}"
    L = ["# Paper-growth experiment: $300 to $350 from trading profits only", "",
         f"Started {s.started.date()} ({s.elapsed_days} days ago). Paper mode, BTC/USDT spot, v2 frozen: **{'YES' if s.frozen else 'NO: a frozen file changed'}**. "
         f"External contributions: **${s.contributions:,.2f}** (must stay 0).", "",
         "## Equity", "",
         f"- Start ${s.start_equity:,.2f} | target ${TARGET_EQUITY:,.2f}",
         f"- **Realized equity: ${s.realized_equity:,.2f}** (realized P&L {f(s.realized_pnl)}, fees included). Only this counts toward milestones.",
         f"- Marked equity: ${s.marked_equity:,.2f} (unrealized P&L {f(s.unrealized_pnl)}, marked at the "
         f"{s.last_close_date.date() if s.last_close_date is not None else 'n/a'} close {s.last_close:,.0f}). Unrealized gains are not counted as earned.",
         f"- Cash ${s.cash:,.2f}; BTC held {s.held:.5f}", "", "## Milestones (realized equity)", ""]
    for m, d in s.milestones.items():
        status = "secured now" if d["secured_now"] else "not secured"
        when = f"first reached {d['reached'].date()}" if d["reached"] is not None else "not reached yet"
        extra = " (marked equity is above it but it is unrealized)" if (d["marked_now"] and not d["secured_now"]) else ""
        L.append(f"- ${m}: {status}, {when}{extra}")
    L += ["", "Risk per trade stays at v2's schedule at every milestone; nothing is increased on reaching one.", "",
          "## Trading record", "",
          f"- Plans issued {s.plans}, unfilled/cancelled {s.unfilled_plans}, closed trades {len(s.closed)}, "
          f"open trade: {('yes, ' + str(round(s.open_trade['bought'] - s.open_trade['sold'], 5)) + ' BTC @ ' + format(s.open_trade['avg_entry'], ',.0f')) if s.open_trade else 'none'}",
          f"- Win rate {s.win_rate:.0%} | profit factor {s.profit_factor:.2f} | average {s.avg_R:+.2f}R" if s.closed else
          "- No closed trades yet, so there is no win rate, profit factor or R per trade to report.",
          f"- Longest losing streak {s.longest_losing_streak}, current {s.current_losing_streak}",
          f"- Fees logged ${s.fees_logged:.2f}; fees at the model rate (0.1% a side) about ${s.fees_estimated:.2f}",
          f"- Slippage: measured on buys vs the plan limit ${s.slippage_buy_measured:.2f}; sell side cannot be measured from the journal, "
          f"model estimate (0.1% of proceeds) about ${s.slippage_sell_estimated:.2f}",
          f"- Maximum drawdown so far {s.max_dd:.1%} | capital utilisation (BTC value / equity) {s.utilization:.0%} of days on average, "
          f"{s.utilization_in_trade:.0%} while in a trade", "",
          "## Waiting for valid setups", "",
          f"- {s.cards} daily cards since the start; {s.waiting_days} of them ({(s.waiting_days / s.cards if s.cards else 0):.0%}) were waiting days "
          f"(trend/macro gate closed, no pullback, event window, pause or too small for Binance's minimum): {s.reasons or 'none yet'}",
          f"- Days since the last closed trade: {s.days_since_last_trade if s.days_since_last_trade is not None else 'no trade yet'}", ""]
    if band:
        L += ["## Context, not a deadline", "",
              f"Realized equity this far into the experiment would sit at: {band}. The simulations (`RESEARCH.md section 10`) say "
              "$350 is a multi-year outcome (median about 4.5 years in the base case among paths that get there, 80% of base paths by year 10, 53% if the "
              "edge is half what history shows). Being below $300 for long stretches is normal for this strategy.", ""]
    return "\n".join(L)


def init_experiment(force: bool = False) -> str:
    path = PAPER_JOURNAL_PATH
    events = read_events(path)
    if EXPERIMENT_FILE.exists() and not force:
        raise SystemExit("The growth experiment is already initialised. Use --force only if you really want to restart it.")
    if any(e["event"] in ("plan", "buy", "sell") for e in events) and not force:
        raise SystemExit("The paper journal already contains trades; refusing to reset it. Use --force to archive it and start over.")
    arch = ROOT / "journal" / "archive"
    arch.mkdir(parents=True, exist_ok=True)
    stamp = utcnow().strftime("%Y%m%dT%H%M%S")
    if path.exists():
        shutil.copy(path, arch / f"paper_journal_{stamp}_before_300_experiment.csv")
        path.unlink()
    now = utcnow()
    append_event(path, event="deposit", usdt=START_EQUITY, note="paper-growth experiment start: 300 USDT, no further contributions",
                 time_utc=now.isoformat())
    EXPERIMENT_FILE.write_text(json.dumps({
        "started_utc": now.isoformat(), "start_equity": START_EQUITY, "target_equity": TARGET_EQUITY, "milestones": list(MILESTONES),
        "contributions_allowed": 0, "mode": "paper", "rules": "v2 frozen",
        "old_journal_archived_as": f"journal/archive/paper_journal_{stamp}_before_300_experiment.csv"}, indent=1), encoding="utf-8")
    return f"Paper-growth experiment started: {START_EQUITY:.0f} USDT at {now.isoformat()} (previous journal archived)."


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Track the $300 -> $350 paper-growth experiment (read-only).")
    ap.add_argument("--init", action="store_true", help="start the experiment: archive the old paper journal and deposit 300 USDT")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--refresh", action="store_true", help="re-download market data first")
    ap.add_argument("--no-context", action="store_true", help="skip the simulation band (faster)")
    args = ap.parse_args(argv)
    if args.init:
        print(init_experiment(args.force))
    from spot_trd.data import load_data
    btc, _ = load_data(args.refresh)
    s = compute(btc=btc)
    band = None if args.no_context else context_band(s.elapsed_days / 365.25)
    text = format_report(s, band)
    REPORTS_DIR.mkdir(exist_ok=True)
    REPORT_FILE.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
