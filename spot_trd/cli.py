"""Single entry point: `uv run spot <command>`."""
import os
import subprocess
import sys
import time
from pathlib import Path

from spot_trd.clock import local_hm
from spot_trd.config import ROOT
from spot_trd.journal import utcnow

MODE_FILE = ROOT / "journal" / "mode"
JOURNAL_COMMANDS = ("deposit", "buy", "sell", "cancel", "skip", "note", "status")
MONITOR_COMMANDS = ("watch", "start", "stop", "last", "autostart", "dashboard")
STARTUP_FILE = (Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
                / "Startup" / "spot-trd-monitor.vbs")

USAGE = """spot: halal BTC spot trading assistant (mode: {mode})

Daily
  spot today                 trade card + live price + chart (run after the daily close, 06:00 UTC+6)
  spot buy  --usdt X --btc Y log a filled limit buy (numbers from Binance order history)
  spot sell --usdt X --btc Y log a sell (stop hit, trend exit, ...)
  spot cancel                you cancelled a plan's unfilled orders
  spot note "text"           log a mistake, emotion or deviation
  spot status                cash, open position, closed trades

Weekly / after each closed trade
  spot review                post-mortem: mistakes and lessons
  spot validate              health scorecard: data, exchange, live vs backtest
  spot shadow                what following every card would have made vs what you actually did
  spot decisions             the system's daily decisions vs what BTC did next (which rules help/hurt)
  spot capital               is v2 worth continuing at your capital? profit per capital level, +$25/50/100 a year, 2030 horizon
  spot limit-entry           execution comparison for frozen v2 signals (analysis; default stays: no manual limit buy)
  spot growth                $300 -> $350 paper-growth experiment: realized vs unrealized equity, milestones, drawdown, waiting time

Analysis
  spot chart                 live chart only
  spot backtest              full historical backtest report
  spot research              compare rule variants (walk-forward)
  spot upgrades              re-test the research-sourced upgrade ideas (pre-registered rule)
  spot laya-eval             re-run the Laya evaluation (GPU)
  spot audit                 profitability audit: realistic fills, walk-forward, baselines, dollars per capital
  spot universe              small multi-asset study (research only; only BTC is tradable)

Always-on monitor + live dashboard
  spot start                 run the monitor in the background and open the dashboard page
  spot dashboard             refresh the dashboard page now and open it in your browser
  spot stop                  stop the background monitor
  spot last                  quick text view: monitor status, decision, alerts (--full: whole card)
  spot autostart on|off      start the monitor automatically when you log in to Windows
  spot watch                 run the monitor in this window (Ctrl+C to stop)

Cloud (GitHub Actions; runs while your PC is off)
  spot sync                  push/pull the journal (automatic if cloud_sync: true). Away from the PC, reply to a card's
                             GitHub issue or email: skip | bought <usdt> <btc> | sold <usdt> <btc> | cancel | note ...

Setup
  spot mode [paper|live]     show or switch mode (paper is the default)
  spot deposit 25            log starting capital (once per mode)

Run any command with -h for its options."""


def get_mode() -> str:
    return MODE_FILE.read_text(encoding="utf-8").strip() if MODE_FILE.exists() else "paper"


def set_mode(mode: str) -> None:
    MODE_FILE.parent.mkdir(parents=True, exist_ok=True)
    MODE_FILE.write_text(mode, encoding="utf-8")


def _spawn_hidden_monitor() -> None:
    # The venv's python.exe/pythonw.exe are uv launchers that start the base python.exe as a child; CREATE_NO_WINDOW
    # gives that whole chain one hidden console, so no terminal window appears (pythonw alone still showed one).
    flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([sys.executable, "-m", "spot_trd.cli", "watch"], cwd=ROOT, creationflags=flags,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def monitor(cmd: str, rest: list[str]) -> None:
    from spot_trd import watch
    from spot_trd.config import load_watch

    cfg = load_watch()
    if cmd == "watch":
        watch.watch(get_mode)
    elif cmd == "start":
        if watch.is_running(cfg):
            print("Monitor is already running. `spot last` shows its latest decision.")
            return
        started = time.time()
        _spawn_hidden_monitor()
        print(f"Monitor started in the background ({get_mode()} mode): daily card at {local_hm('2000-01-01 ' + cfg['daily_run_utc'])}, "
              f"dashboard refreshed every {cfg['price_check_minutes']} min.")
        print("Catching up and checking the market (first check, up to ~1-2 minutes)...")
        while time.time() - started < 150:  # first check refreshes data and replays any missed days
            if watch.STATUS_FILE.exists() and watch.STATUS_FILE.stat().st_mtime >= started:
                print(watch.format_brief(watch.read_status(), running=True))
                if "--no-open" not in rest:
                    os.startfile(watch.DASH_PAGE)
                    print("Dashboard opened (bookmark it; it reloads itself).")
                break
            time.sleep(1)
        else:
            print(f"Still working; `spot last` shows the result. Dashboard: {watch.DASH_PAGE}")
        print("Stop the monitor with `spot stop`.")
    elif cmd == "dashboard":
        try:
            page, _ = watch.update_dashboard(get_mode() == "paper", cfg, watch._read_state()["last_card_day"],
                                             utcnow())
        except RuntimeError as err:
            raise SystemExit(str(err))
        print(watch.format_brief(watch.read_status(), running=watch.is_running(cfg)))
        os.startfile(page)
        print(f"Dashboard opened: {page}" + ("" if watch.is_running(cfg) else
                                              "\nThe monitor isn't running, so it won't update. `spot start` keeps it live."))
    elif cmd == "stop":
        if not watch.is_running(cfg):
            print("Monitor is not running.")
            return
        watch.STOP_FILE.write_text("stop", encoding="utf-8")
        print("Stop requested; the monitor exits within ~5 seconds.")
    elif cmd == "last":
        latest = watch.CARDS_DIR / "latest.txt"
        age = watch.heartbeat_age()
        status = f"RUNNING (last check {age / 60:.0f} min ago)" if watch.is_running(cfg) else "STOPPED"
        print(f"Monitor: {status} | mode: {get_mode()}\n")
        print(watch.format_brief(watch.read_status(), running=watch.is_running(cfg)) + "\n")
        if "--full" in rest:
            print(latest.read_text(encoding="utf-8") if latest.exists() else "No card yet. Run `spot today` or `spot start`.")
        else:
            print("Full card: `spot last --full`.")
        if watch.LOG_FILE.exists():
            events = [l for l in watch.LOG_FILE.read_text(encoding="utf-8").splitlines() if " EVENT " in l][-5:]
            print("\nRecent events:\n" + ("\n".join(events) or "none"))
        print(f"\nDashboard: {watch.DASH_PAGE}")
    elif cmd == "autostart":
        if not rest or rest[0] not in ("on", "off"):
            print(f"Autostart is {'ON' if STARTUP_FILE.exists() else 'OFF'}. Use `spot autostart on|off`.")
            return
        if rest[0] == "on":
            # Window style 0 = hidden, so nothing flashes at login.
            STARTUP_FILE.write_text(
                f'CreateObject("WScript.Shell").Run """{sys.executable}"" -m spot_trd.cli watch", 0, False\r\n',
                encoding="utf-8")
            print(f"Autostart ON: the monitor starts hidden each time you log in ({STARTUP_FILE}).\n"
                  "Run `spot start` to start it right now too.")
        else:
            STARTUP_FILE.unlink(missing_ok=True)
            print("Autostart OFF. A running monitor keeps going until `spot stop`.")


def sync(quiet: bool = False) -> None:
    """Push your journal and pull what the cloud and your GitHub replies wrote."""
    from spot_trd.gitsync import sync as git_sync
    git_sync(quiet=quiet)


def pull_first() -> None:
    """Before reading the journal: fetch anything logged from your phone (GitHub replies) or by the cloud card."""
    from spot_trd.config import load_watch
    if load_watch().get("cloud_sync"):
        sync(quiet=True)


def _call(module_main, args: list[str]) -> None:
    saved = sys.argv
    sys.argv = ["spot", *args]
    try:
        module_main()
    finally:
        sys.argv = saved


def main() -> None:
    args = sys.argv[1:]
    mode = get_mode()
    if not args or args[0] in ("-h", "--help", "help"):
        if not args:
            from spot_trd import watch
            from spot_trd.config import load_watch
            print(watch.format_brief(watch.read_status(), running=watch.is_running(load_watch())) + "\n")
        print(USAGE.format(mode=mode))
        return
    cmd, rest = args[0], args[1:]
    paper = ["--paper"] if mode == "paper" else []

    if cmd == "mode":
        if not rest:
            print(f"Mode: {mode}")
            return
        if rest[0] not in ("paper", "live"):
            raise SystemExit("Usage: spot mode [paper|live]")
        set_mode(rest[0])
        print(f"Mode set to {rest[0]}." + (
            " Cards and logs now track REAL money in journal/trading_journal.csv. Log your capital with "
            "`spot deposit <usdt>` if you haven't." if rest[0] == "live" else " Using journal/paper_journal.csv."))
    elif cmd in MONITOR_COMMANDS:
        monitor(cmd, rest)
    elif cmd == "sync":
        sync()
    elif cmd == "today":
        from spot_trd import run
        pull_first()
        _call(run.main, paper + rest)
        pull_first()  # push the plan the card just recorded, so the cloud card sees it
    elif cmd in JOURNAL_COMMANDS:
        from spot_trd import journal
        pull_first()
        journal.main(paper + [cmd, *rest])
        if cmd != "status":
            pull_first()
    elif cmd == "shadow":
        from spot_trd import shadow
        pull_first()
        shadow.main(paper + rest)
    elif cmd == "review":
        from spot_trd import review
        _call(review.main, paper + rest)
    elif cmd == "decisions":
        from spot_trd import decisions
        pull_first()
        _call(decisions.main, paper + rest)
    elif cmd == "capital":
        from spot_trd import capital
        _call(capital.main, rest)
    elif cmd == "limit-entry":
        from spot_trd import limit_entry
        _call(limit_entry.main, rest)
    elif cmd == "growth":
        from spot_trd import growth
        growth.main(rest)
    elif cmd == "validate":
        from spot_trd import validate
        _call(validate.main, paper + rest)
    elif cmd == "chart":
        from spot_trd import chart
        _call(chart.main, rest)
    elif cmd == "backtest":
        from spot_trd import report
        _call(report.main, rest)
    elif cmd == "research":
        from spot_trd import research
        _call(research.main, rest)
    elif cmd == "upgrades":
        from spot_trd import upgrades
        _call(upgrades.main, rest)
    elif cmd == "audit":
        from spot_trd import audit
        _call(audit.main, rest)
    elif cmd == "universe":
        from spot_trd import universe
        _call(universe.main, rest)
    elif cmd == "laya-eval":
        from spot_trd import laya_eval
        _call(laya_eval.main, rest)
    else:
        print(f"Unknown command '{cmd}'.\n")
        print(USAGE.format(mode=mode))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
