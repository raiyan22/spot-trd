"""Always-on monitor: daily card after the UTC close, and a live HTML dashboard refreshed on every check."""
import json
import logging
import sys
import time
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler

import pandas as pd

from spot_trd.clock import local, local_hm
from spot_trd.config import JOURNAL_PATH, PAPER_JOURNAL_PATH, ROOT, load_rules, load_watch
from spot_trd.journal import Book, load_book, utcnow
from spot_trd.run import trailing_stop

STATE_DIR = ROOT / "journal"
STATE_FILE = STATE_DIR / "watch_state.json"
STOP_FILE = STATE_DIR / "watch.stop"
HEARTBEAT_FILE = STATE_DIR / "watch.heartbeat"
CARDS_DIR = ROOT / "reports" / "cards"
LOG_FILE = ROOT / "logs" / "watch.log"
DASH_PAGE = ROOT / "dashboard" / "index.html"
STATUS_FILE = STATE_DIR / "status.json"  # summary of the last check, printed in the terminal by `spot start/last`
STATUS_KEYS = ("generated_at", "next_card_at", "mode", "headline", "kind", "steps", "alerts", "data_issues", "live",
               "live_change", "equity", "focus")
APP_ID = "spot-trd"
PULL_MINUTES = 30  # how often the monitor pulls the journal from GitHub (fills you logged by replying there)

log = logging.getLogger("spot_trd.watch")


@dataclass
class Alert:
    key: str
    title: str
    message: str


def check_alerts(feat: pd.DataFrame, book: Book, rules: dict, ticker: dict, now: pd.Timestamp, cfg: dict) -> list[Alert]:
    """Conditions worth your attention. Pure function: no I/O."""
    px, day = ticker["last"], now.date()
    offset = rules["exit"]["stop_limit_offset"]
    out = []

    trade = book.open_trade
    if trade:
        stop, _ = trailing_stop(feat, trade, rules)
        if px <= stop:
            out.append(Alert(f"stop-breach:{trade.trade_id}:{stop:.0f}", "SELL CHECK: price is below your stop",
                             f"BTC {px:,.0f} < stop {stop:,.0f}. Check that your stop order executed on Binance. "
                             "If not, sell at market now, then `spot sell`."))
        elif px <= stop * (1 + cfg["stop_near_pct"]):
            out.append(Alert(f"stop-near:{trade.trade_id}:{day}", "Price is close to your stop",
                             f"BTC {px:,.0f}, stop {stop:,.0f} ({px / stop - 1:+.1%}). Make sure the stop order "
                             f"(market stop, trigger {stop:,.0f}) is live on Binance."))

    active = book.active_plan(now)
    planned = sum(q for _, q in active.plan["orders"]) if active else 0.0
    if active and active.btc_bought < planned - 1e-12:
        stop = active.plan["stop"]
        for price, qty in active.plan["orders"]:
            if px <= price:
                out.append(Alert(f"limit-touch:{active.trade_id}:{price:.0f}", "BUY may have filled",
                                 f"BTC {px:,.0f} reached your limit buy {price:,.0f} ({qty:.5f} BTC). If it filled: "
                                 f"place a market stop (trigger {stop:,.0f}), "
                                 "then `spot buy`."))
        left = pd.Timestamp(active.plan["valid_until"]) - now
        if pd.Timedelta(0) < left <= pd.Timedelta(minutes=cfg["expiry_warn_minutes"]):
            out.append(Alert(f"expiry:{active.trade_id}", "Cancel unfilled limit buys soon",
                             f"Plan {active.trade_id} expires at {local(active.plan['valid_until'])}. "
                             "Cancel any unfilled buys on Binance then."))

    last = feat.iloc[-1]
    if trade is None and active is None and last["regime_ok"]:
        trigger = last["ema_pb"] * (1 + rules["setup"]["pullback_tolerance"])
        if px <= trigger * (1 + cfg["setup_near_pct"]):
            out.append(Alert(f"setup-near:{day}", "Buy setup may form at today's close",
                             f"BTC {px:,.0f} is near the trigger {trigger:,.0f}. Nothing to do now; "
                             "the next daily card will say if there's a buy plan."))
    return out


def daily_due(now: pd.Timestamp, last_card_day: str | None, run_at: str) -> bool:
    hh, mm = map(int, run_at.split(":"))
    return str(now.date()) != last_card_day and now >= now.normalize() + pd.Timedelta(hours=hh, minutes=mm)


def notify(cfg: dict, title: str, message: str, launch: str = "") -> None:
    """Log every event; show a Windows pop-up only if desktop_notifications is on in config/watch.yaml."""
    log.info("EVENT %s | %s", title, message)
    if not cfg.get("desktop_notifications"):
        return
    try:
        from winotify import Notification, audio

        toast = Notification(app_id=APP_ID, title=title, msg=message[:250], duration="long", launch=launch)
        toast.set_audio(audio.Default, loop=False)
        toast.show()
    except Exception as err:  # best-effort; the dashboard and log still show everything
        log.warning("desktop notification failed: %s", err)


def _read_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"last_card_day": None, "sent": {}}


def _write_state(state: dict) -> None:
    cutoff = (utcnow() - pd.Timedelta(days=14)).isoformat()
    state["sent"] = {k: v for k, v in state["sent"].items() if v >= cutoff}
    STATE_FILE.write_text(json.dumps(state, indent=1), encoding="utf-8")


def heartbeat_age() -> float | None:
    if not HEARTBEAT_FILE.exists():
        return None
    return time.time() - HEARTBEAT_FILE.stat().st_mtime


def is_running(cfg: dict) -> bool:
    age = heartbeat_age()
    return age is not None and age < cfg["price_check_minutes"] * 60 * 2 + 60


def _setup_logging() -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    fmt = logging.Formatter("%(asctime)s UTC %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
    fmt.converter = time.gmtime  # same clock as the cards and Binance's daily close
    handler.setFormatter(fmt)
    log.addHandler(handler)
    if sys.stderr is not None:  # None when running hidden under pythonw
        log.addHandler(logging.StreamHandler())
    log.setLevel(logging.INFO)


def run_daily(paper: bool, cfg: dict, announce_failure: bool = True) -> bool:
    """Refresh market data, make today's card (recording any new buy plan) and save it."""
    from spot_trd.run import produce_card

    if cfg.get("cloud_sync"):
        from spot_trd.gitsync import sync
        sync(quiet=True)  # pull the cloud's card and your phone replies first, so a plan isn't recorded twice
    text, ok = produce_card(paper, live=False)
    if cfg.get("cloud_sync"):
        sync(quiet=True)
    day = str(utcnow().date())
    CARDS_DIR.mkdir(parents=True, exist_ok=True)
    path = CARDS_DIR / f"card_{day}{'_paper' if paper else ''}.txt"
    path.write_text(text, encoding="utf-8")
    (CARDS_DIR / "latest.txt").write_text(text, encoding="utf-8")
    headline = next((l for l in text.splitlines() if l.startswith(">>> TODAY:")), ">>> TODAY: see card")
    action = headline.removeprefix(">>> TODAY: ")
    quiet = (action.startswith("NO ACTION") and not cfg["notify_no_trade"]) or (not ok and not announce_failure)
    if not quiet:
        notify(cfg, f"BTC {'(paper) ' if paper else ''}decision for {day}", action, launch=str(DASH_PAGE))
    log.info("daily card %s ok=%s: %s", day, ok, action)
    return ok


def update_dashboard(paper: bool, cfg: dict, last_card_day: str | None, now: pd.Timestamp) -> tuple[str, list[Alert]]:
    """Recompute the decision and alerts from cached daily data + the live price, and rewrite the HTML page."""
    from spot_trd.chart import live_snapshot
    from spot_trd.config import load_events, load_universe
    from spot_trd.dashboard import build_context, write_dashboard
    from spot_trd.data import load_data
    from spot_trd.regime import build_features
    from spot_trd.validate import data_checks

    rules, universe, events = load_rules(), load_universe(), load_events()
    book = load_book(rules, PAPER_JOURNAL_PATH if paper else JOURNAL_PATH)
    if book.breaker is None:
        raise RuntimeError("no capital logged yet: run `uv run spot deposit 25`")
    btc, macro = load_data(refresh=False)
    feat = build_features(btc, macro, rules)
    extra: list[Alert] = []
    try:
        ticker, h4 = live_snapshot(rules["market"]["symbol"])
    except Exception as err:  # the decision stands without live context
        ticker, h4 = None, None
        extra.append(Alert("live-fail", "Live price unavailable", f"{err}. The decision is still valid; retrying."))
    issues = []
    for c in data_checks(btc, macro, feat, events, now):
        if c.status != "FAIL":
            continue
        if c.name == "BTC data fresh" and last_card_day != str(now.date()):
            extra.append(Alert("card-pending", "Today's daily card is pending",
                               f"It runs at {local_hm('2000-01-01 ' + cfg['daily_run_utc'])} (and retries if the download failed). "
                               "The decision shown is from the previous daily close."))
        else:
            issues.append(f"{c.name}: {c.detail}")
    alerts = check_alerts(feat, book, rules, ticker, now, cfg) if ticker else []
    ctx = build_context(feat, book, rules, universe, events, ticker, h4, alerts + extra, paper, now,
                        data_issues=issues, run_at=cfg["daily_run_utc"])
    STATUS_FILE.write_text(json.dumps({k: ctx[k] for k in STATUS_KEYS}, default=str, indent=1), encoding="utf-8")
    return write_dashboard(ctx), alerts


def format_brief(status: dict | None, running: bool | None = None) -> str:
    """A few lines for the terminal: the decision, what to do, price, equity and alerts."""
    if not status:
        return "No status yet: start the monitor (`spot start`) or run `spot today`."
    bar = "-" * 78
    label, pct, sub = status["focus"]
    focus = f"{label} {pct:+.1%} ({sub})" if pct is not None else sub
    change = f" (24h {status['live_change']:+.1f}%)" if status["live_change"] is not None else ""
    head = f" spot-trd | {status['mode']}"
    if running is not None:
        head += f" | monitor {'RUNNING' if running else 'STOPPED'}"
    head += f" | updated {local(status['generated_at'])}"
    lines = [bar, head, f" TODAY: {status['headline']}"]
    lines += [f"   - {s}" for s in status["steps"]]
    lines.append(f" BTC {status['live']:,.0f}{change} | equity {status['equity']:,.2f} USDT | {focus}")
    alerts = [f"{a['title']}: {a['message']}" for a in status["alerts"]] + [f"DATA: {i}" for i in status["data_issues"]]
    lines += [" Alerts: none"] if not alerts else [" Alerts:"] + [f"   ! {a}" for a in alerts]
    latest = CARDS_DIR / "latest.txt"
    if latest.exists():
        from spot_trd.catchup import HEADER

        card = latest.read_text(encoding="utf-8").splitlines()
        start = next((i for i, l in enumerate(card) if l.startswith(HEADER)), None)
        if start is not None:
            block = card[start:]
            lines += [" " + l for l in block[:next((i for i, l in enumerate(block) if not l.strip()), len(block))]]
    lines += [f" Next daily card: {local(status['next_card_at'])} | dashboard: {DASH_PAGE}", bar]
    return "\n".join(lines)


def read_status() -> dict | None:
    try:
        return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def watch(get_mode) -> None:
    """Main loop. Stops when `spot stop` creates the stop file, or on Ctrl+C."""
    _setup_logging()
    cfg = load_watch()
    if is_running(cfg):
        raise SystemExit("The monitor is already running. Use `spot stop` first.")
    STOP_FILE.unlink(missing_ok=True)
    state = _read_state()
    log.info("monitor started: daily card at %s UTC, checks every %s min", cfg["daily_run_utc"], cfg["price_check_minutes"])
    failures = 0
    last_pull = None
    try:
        while not STOP_FILE.exists():
            now = utcnow()
            paper = get_mode() == "paper"
            HEARTBEAT_FILE.write_text(now.isoformat(), encoding="utf-8")
            try:
                if cfg.get("cloud_sync") and (last_pull is None or now - last_pull >= pd.Timedelta(minutes=PULL_MINUTES)):
                    from spot_trd.gitsync import sync
                    sync(quiet=True)  # fills you logged by replying on GitHub reach the dashboard and alerts
                    last_pull = now
                if daily_due(now, state["last_card_day"], cfg["daily_run_utc"]):
                    today = str(now.date())
                    if run_daily(paper, cfg, announce_failure=state.get("fail_day") != today):
                        state["last_card_day"] = today
                    else:
                        state["fail_day"] = today  # retry every check, but report the failure once a day
                    _write_state(state)
                _, alerts = update_dashboard(paper, cfg, state["last_card_day"], now)
                if sys.stdout is not None and sys.stdout.isatty():  # `spot watch` in a visible window
                    print(format_brief(read_status()), flush=True)
                for a in alerts:
                    if a.key not in state["sent"]:
                        notify(cfg, a.title, a.message, launch=str(DASH_PAGE))
                        state["sent"][a.key] = now.isoformat()
                        _write_state(state)
                failures = 0
            except Exception as err:  # keep running through network blips
                failures += 1
                log.warning("check failed (%d in a row): %s", failures, err)
            deadline = time.time() + cfg["price_check_minutes"] * 60
            while time.time() < deadline and not STOP_FILE.exists():
                time.sleep(5)
    except KeyboardInterrupt:
        pass
    finally:
        STOP_FILE.unlink(missing_ok=True)
        HEARTBEAT_FILE.unlink(missing_ok=True)
        log.info("monitor stopped")
