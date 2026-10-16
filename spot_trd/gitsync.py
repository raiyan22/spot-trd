"""Keep the journal in step between this PC and GitHub, where the cloud runner and your issue replies also write it.

The journal CSVs are append-only and use git's union merge (.gitattributes), so rows written on both sides at the
same time are both kept; load_book counts a plan recorded twice for the same close once.
"""
import subprocess

from spot_trd.config import ROOT
from spot_trd.journal import utcnow

SYNC_FILES = ("journal/paper_journal.csv", "journal/trading_journal.csv", "journal/mode",
              "journal/decisions.csv", "journal/decisions_paper.csv")


def git(*a: str, timeout: int = 60) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as err:
        return subprocess.CompletedProcess(a, 1, "", str(err))


def commit_journal(message: str | None = None) -> None:
    files = [f for f in SYNC_FILES if (ROOT / f).exists()]
    git("add", *files)
    if git("diff", "--cached", "--quiet").returncode:
        git("commit", "-m", message or f"journal update {utcnow():%Y-%m-%d %H:%M} UTC")


def sync(message: str | None = None, quiet: bool = False, attempts: int = 3) -> bool:
    """Commit local journal changes, pull what the cloud wrote, push. Returns True on success."""
    if not git("remote").stdout.strip():
        if not quiet:
            print("Cloud sync: no GitHub remote set up yet (see guide section 2, 'Run it in the cloud').")
        return False
    commit_journal(message)
    err = ""
    for _ in range(attempts):  # a push can lose a race with the cloud; pull again and retry
        pull = git("pull", "--rebase", "--autostash", "origin", "main")
        if pull.returncode:
            git("rebase", "--abort")
            err = pull.stderr
            continue
        ahead = git("rev-list", "--count", "origin/main..HEAD").stdout.strip()
        push = git("push", "origin", "HEAD:main") if ahead not in ("", "0") else pull
        if push.returncode == 0:
            if not quiet:
                print("Cloud sync: journal up to date with GitHub (the cloud and your replies see the same journal).")
            return True
        err = push.stderr
    lines = err.strip().splitlines()
    print(f"Cloud sync FAILED ({lines[-1] if lines else 'unknown error'}). Your journal is safe locally; retry `spot sync`.")
    return False
