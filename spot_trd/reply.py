"""Your replies to a card's GitHub issue (a comment, or a reply to the notification email), logged into the journal.

Runs in GitHub Actions (.github/workflows/reply.yml) when the repo owner comments; anyone else is ignored there. It
first records any buy plan the cloud card announced, applies the command through the same `journal` code the PC uses
(so the same checks apply: no buy without a plan, no buy above cash, spot only), pushes the journal, and answers in
the issue. The PC pulls the change the next time you run a `spot` command (the monitor pulls every 30 minutes).
"""
import contextlib
import io
import os
import re
import subprocess
import sys

import pandas as pd

from spot_trd.clock import from_local, local

HELP = """How to reply (one line, as the first line of a comment or of your email reply):
  skip                          you won't place this plan's orders
  bought <USDT> <BTC>           a buy filled: USDT spent and BTC received, from Binance's order history
                                e.g.  bought 6.49 0.0000799   (add the fill time if it wasn't today: bought 6.49 0.0000799 2026-10-16 20:05)
  sold <USDT> <BTC>             you sold (stop hit or exit): USDT received and BTC sold
  cancel                        you cancelled the plan's unfilled orders
  note <text>                   anything worth remembering
  status                        cash, position and the shadow book
Times are your time (UTC+6), as Binance shows them on your phone. Each fill is one reply; for two fills, reply twice."""

VERBS = {"skip": "skip", "skipped": "skip", "bought": "buy", "buy": "buy", "filled": "buy", "sold": "sell",
         "sell": "sell", "cancel": "cancel", "cancelled": "cancel", "canceled": "cancel", "note": "note",
         "status": "status", "help": "help", "?": "help"}
NUMBER = re.compile(r"\d*\.?\d+(?:[eE]-?\d+)?")
WHEN = re.compile(r"(\d{4}-\d{2}-\d{2})(?:[ T](\d{1,2}:\d{2}))?")


def first_line(body: str) -> str:
    """The command line of a comment or email reply: quoted text and the email's 'On ... wrote:' tail are ignored."""
    for raw in body.splitlines():
        line = raw.strip().strip("`*_ ")
        if not line or line.startswith(">"):
            continue
        if re.match(r"^on .+wrote:?$", line, re.I):
            break
        return line
    return ""


def parse(body: str, at: pd.Timestamp) -> tuple[str, list[str]]:
    """(command, journal arguments). Raises ValueError with a message meant for you."""
    line = first_line(body)
    verb, _, rest = line.partition(" ")
    cmd = VERBS.get(verb.lower().rstrip(":.,!"))
    if cmd is None:
        raise ValueError(f"I didn't recognise `{line[:80]}`." if line else "The reply was empty.")
    rest = rest.strip()
    if cmd in ("buy", "sell"):
        when = at
        m = WHEN.search(rest)
        if m:
            when = from_local(f"{m.group(1)} {m.group(2) or '12:00'}")
            rest = rest.replace(m.group(0), " ")
        nums = [float(x) for x in NUMBER.findall(rest.replace(",", " "))]
        if len(nums) != 2:
            raise ValueError(f"`{cmd_word(cmd)}` needs two numbers, USDT and BTC (got `{line[:80]}`).")
        usdt, btc = max(nums), min(nums)  # BTC amounts here are always below 1, USDT amounts at least 5
        if btc <= 0 or btc >= 1 or usdt < 1:
            raise ValueError(f"Those numbers don't look like USDT and BTC amounts: `{line[:80]}`.")
        if when > at + pd.Timedelta(minutes=5):
            raise ValueError(f"The fill time {local(when)} is in the future.")
        return cmd, [cmd, "--usdt", f"{usdt:.8f}", "--btc", f"{btc:.8f}", "--time", when.isoformat(),
                     "--note", "logged from a GitHub reply"]
    if cmd == "note":
        if not rest:
            raise ValueError("`note` needs some text after it.")
        return cmd, ["note", rest[:500]]
    if cmd == "skip":
        return cmd, ["skip", "--note", rest[:200] or "via GitHub reply"]
    return cmd, [cmd]


def cmd_word(cmd: str) -> str:
    return {"buy": "bought", "sell": "sold"}.get(cmd, cmd)


def answer(issue: str, text: str) -> None:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        print(f"(not on GitHub; would reply on #{issue})\n{text}")
        return
    subprocess.run(["gh", "issue", "comment", issue, "--body", text], check=True)


def run(body: str, issue: str, at: pd.Timestamp) -> int:
    from spot_trd import gitsync, journal, shadow
    from spot_trd.cloud import paper_mode
    from spot_trd.config import JOURNAL_PATH, PAPER_JOURNAL_PATH, load_rules
    from spot_trd.data import load_data
    from spot_trd.regime import build_features
    from spot_trd.run import produce_card

    try:
        cmd, args = parse(body, at)
    except ValueError as err:
        answer(issue, f"Not recorded: {err}\n\n```\n{HELP}\n```")
        return 0
    if cmd == "help":
        answer(issue, f"```\n{HELP}\n```")
        return 0
    paper = paper_mode()
    path = PAPER_JOURNAL_PATH if paper else JOURNAL_PATH
    rules = load_rules()
    try:  # record any plan the cloud card announced but no PC has recorded yet
        produce_card(paper, refresh=True, record=True, live=False)
    except Exception as err:
        print(f"card refresh failed: {err}")
    out = io.StringIO()
    if cmd != "status":
        try:
            with contextlib.redirect_stdout(out):
                journal.main(args, path=path)
        except SystemExit as err:
            if err.code not in (None, 0):
                answer(issue, f"Not recorded: {err.code}\n\n```\n{HELP}\n```")
                return 0
        if not gitsync.sync(message=f"journal: {cmd_word(cmd)} from GitHub reply #{issue}", quiet=True):
            answer(issue, "NOT saved: the journal couldn't be pushed (GitHub error). Please send the same reply again.")
            return 1
    book = journal.load_book(rules, path)
    try:
        btc, macro = load_data(refresh=False)
        extra = shadow.card_lines(book, build_features(btc, macro, rules), rules)
    except Exception as err:
        extra = [f"(shadow book unavailable: {err})"]
    head = "Status" if cmd == "status" else f"Recorded: `{first_line(body)[:80]}`"
    logged = [ln for ln in out.getvalue().splitlines() if ln.startswith("Logged")]
    body_text = "\n".join(logged + ["", journal.status_text(book), "", *extra]).strip()
    answer(issue, f"{head}{' (paper)' if paper else ''}\n\n```\n{body_text}\n```\n"
                  "Your PC picks this up the next time you run a `spot` command.")
    return 0


def main() -> None:
    at = pd.Timestamp(os.environ.get("COMMENT_TIME") or pd.Timestamp.now(tz="UTC"))
    at = (at.tz_convert("UTC").tz_localize(None) if at.tzinfo else at).floor("s")
    sys.exit(run(os.environ.get("COMMENT_BODY", ""), os.environ.get("ISSUE_NUMBER", "0"), at))


if __name__ == "__main__":
    main()
