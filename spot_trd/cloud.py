"""Cloud runner (GitHub Actions): the daily card and price alerts while your PC is off.

Read-only by design: it never writes the journal or the decision log, so it can't conflict with the PC. It reads the
journal you pushed with `spot sync` (open trade, stop, active plan) and notifies you:
  - always: a summary and the card on the Actions run page, plus the dashboard page as a downloadable artifact;
  - when there is something to do: a GitHub issue in the repo (GitHub emails / pushes it to your phone app),
    plus an ntfy.sh push if the NTFY_TOPIC secret is set.
A buy plan the cloud announces is recorded on your PC by the catch-up the next time you run `spot today` or `spot start`.

    python -m spot_trd.cloud daily     # after the 00:00 UTC close
    python -m spot_trd.cloud check     # live-price alerts (stop near/hit, limit touched, expiry)
"""
import os
import subprocess
import sys

import pandas as pd

from spot_trd.config import JOURNAL_PATH, PAPER_JOURNAL_PATH, ROOT, load_rules, load_watch
from spot_trd.journal import load_book, utcnow

MODE_FILE = ROOT / "journal" / "mode"


def paper_mode() -> bool:
    return not MODE_FILE.exists() or MODE_FILE.read_text(encoding="utf-8").strip() == "paper"


def summary(text: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"```\n{text}\n```\n")
    print(text)


def _issue_exists(key: str) -> bool:
    out = subprocess.run(["gh", "issue", "list", "--state", "all", "--limit", "200", "--json", "title", "--jq", ".[].title"],
                         capture_output=True, text=True, check=True).stdout
    return any(f"[{key}]" in t for t in out.splitlines())


def notify(key: str, title: str, body: str) -> None:
    """One notification per key (a day's card, or one alert), however often the job runs."""
    if os.environ.get("GITHUB_ACTIONS") != "true":
        print(f"(not on GitHub; would notify) [{key}] {title}")
        return
    if _issue_exists(key):
        print(f"already notified: {key}")
        return
    subprocess.run(["gh", "issue", "create", "--title", f"[{key}] {title}"[:250], "--body", f"```\n{body}\n```"],
                   check=True)
    topic = os.environ.get("NTFY_TOPIC")
    if topic:
        import requests

        requests.post(f"https://ntfy.sh/{topic}", data=body[:3500].encode("utf-8"),
                      headers={"Title": title[:200].encode("utf-8"), "Priority": "high"}, timeout=30)


def dashboard(paper: bool) -> None:
    """Rebuild the dashboard page (uploaded as a run artifact) and put the terminal summary at the top of the run page."""
    from spot_trd.watch import format_brief, read_status, update_dashboard

    try:
        update_dashboard(paper, load_watch(), str(utcnow().date()), utcnow())
        summary(format_brief(read_status()))
    except Exception as err:  # the card and notifications don't depend on it
        print(f"dashboard skipped: {err}")


def daily() -> int:
    from spot_trd.run import produce_card

    paper = paper_mode()
    text, ok = produce_card(paper, refresh=True, record=False, live=False)
    dashboard(paper)
    summary(text)
    headline = next((l for l in text.splitlines() if l.startswith(">>> TODAY:")), ">>> TODAY: see card")
    headline = headline.removeprefix(">>> TODAY: ")
    day = str(utcnow().date())
    if not ok or not headline.startswith("NO ACTION"):
        extra = ("\n\nBuy plan: run `uv run spot today` on your PC to record it (or `spot start`), then place the "
                 "orders shown." if headline.startswith("PLACE") else "")
        notify(f"card {day}", f"{'(paper) ' if paper else ''}{headline}", text + extra)
    return 0


def check() -> int:
    from spot_trd.chart import live_snapshot
    from spot_trd.data import load_data
    from spot_trd.regime import build_features
    from spot_trd.watch import check_alerts

    paper, rules, cfg = paper_mode(), load_rules(), load_watch()
    book = load_book(rules, PAPER_JOURNAL_PATH if paper else JOURNAL_PATH)
    now = utcnow()
    if book.breaker is None or (book.open_trade is None and book.active_plan(now) is None and not cfg["cloud_setup_alerts"]):
        print("No open trade or active plan: nothing to watch between daily cards.")
        return 0
    btc, macro = load_data(refresh=True)
    feat = build_features(btc, macro, rules)
    ticker, _ = live_snapshot(rules["market"]["symbol"])
    alerts = check_alerts(feat, book, rules, ticker, now, cfg)
    dashboard(paper)
    summary(f"BTC {ticker['last']:,.0f} at {now:%Y-%m-%d %H:%M} UTC. Alerts: {len(alerts) or 'none'}")
    for a in alerts:
        notify(a.key, a.title, a.message)
    return 0


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "daily"
    if cmd not in ("daily", "check"):
        raise SystemExit("Usage: python -m spot_trd.cloud daily|check")
    raise SystemExit(daily() if cmd == "daily" else check())


if __name__ == "__main__":
    main()
