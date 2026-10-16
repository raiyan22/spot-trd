"""Cloud runner (GitHub Actions): the daily card and price alerts while your PC is off.

It reads the journal (open trade, stop, active plan) and notifies you:
  - always: a summary and the card on the Actions run page, plus the dashboard page as a downloadable artifact;
  - when there is something to do: a GitHub issue in the repo (GitHub emails / pushes it to your phone app),
    plus an ntfy.sh push if the NTFY_TOPIC secret is set. You answer by replying (see spot_trd/reply.py).
The daily job records the card's decision and any buy plan in the journal and pushes it (so the shadow book tracks
every plan even when the PC is off); the price checks stay read-only. The PC pulls before it writes.

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
    owner = os.environ.get("GITHUB_REPOSITORY_OWNER")
    mention = f"@{owner} " if owner else ""  # GitHub emails @mentions by default, even without watching the repo
    subprocess.run(["gh", "issue", "create", "--title", f"[{key}] {title}"[:250],
                    "--body", f"{mention}{title}\n\n{reply_hint(title)}\n\n```\n{body}\n```"], check=True)
    topic = os.environ.get("NTFY_TOPIC")
    if topic:
        import requests

        requests.post(f"https://ntfy.sh/{topic}", data=body[:3500].encode("utf-8"),
                      headers={"Title": title[:200].encode("utf-8"), "Priority": "high"}, timeout=30)


def reply_hint(title: str) -> str:
    """Tell the user how to report back, in the notification itself (issue body and the email GitHub sends)."""
    t = title.upper()
    lines = ["**Tell the system what you did:** reply to this email, or comment on this issue (first line only; "
             "a bot confirms within a few minutes)."]
    if any(w in t for w in ("PLACE", "KEEP", "LIMIT", "BUY")):
        lines += ["- Won't place the orders: `skip`",
                  "- A buy filled: `bought <USDT spent> <BTC received>`, e.g. `bought 6.49 0.0000799` (one reply per fill)"]
    if any(w in t for w in ("HOLD", "STOP", "SELL", "CHECK")):
        lines += ["- You sold or the stop hit: `sold <USDT received> <BTC sold>`, e.g. `sold 6.62 0.0000799`"]
    lines += ["- Also: `cancel` (unfilled orders cancelled), `note <text>`, `status`, `help`. "
              "Saying nothing counts as not placed; the shadow book still tracks what following the card would do."]
    return "\n".join(lines)


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
    on_github = os.environ.get("GITHUB_ACTIONS") == "true"
    text, ok = produce_card(paper, refresh=True, record=on_github, live=False)
    if on_github:
        from spot_trd.gitsync import sync

        if not sync(message=f"cloud card {utcnow():%Y-%m-%d}", quiet=True):
            text += "\n\n[WARN] The cloud couldn't save today's card to the journal; your PC will record it when it runs."
    dashboard(paper)
    summary(text)
    headline = next((l for l in text.splitlines() if l.startswith(">>> TODAY:")), ">>> TODAY: see card")
    headline = headline.removeprefix(">>> TODAY: ")
    day = str(utcnow().date())
    if not ok or not headline.startswith("NO ACTION"):
        notify(f"card {day}", f"{'(paper) ' if paper else ''}{headline}", text)
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


def test() -> int:
    """Send one notification through the real path, to confirm email / phone delivery."""
    now = utcnow()
    notify(f"test {now:%Y-%m-%d %H:%M}", "Test notification: spot-trd can reach you",
           "This is a test. Real notifications look like this and arrive only when there is something to do. "
           "You can close this issue.")
    return 0


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "daily"
    jobs = {"daily": daily, "check": check, "test": test}
    if cmd not in jobs:
        raise SystemExit("Usage: python -m spot_trd.cloud daily|check|test")
    raise SystemExit(jobs[cmd]())


if __name__ == "__main__":
    main()
