from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
RAW_DIR = ROOT / "data" / "raw"
REPORTS_DIR = ROOT / "reports"
JOURNAL_PATH = ROOT / "journal" / "trading_journal.csv"
PAPER_JOURNAL_PATH = ROOT / "journal" / "paper_journal.csv"


def _load(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_rules(path: Path | None = None) -> dict:
    return _load(path or CONFIG_DIR / "rules.yaml")


def load_universe(path: Path | None = None) -> dict:
    return _load(path or CONFIG_DIR / "halal_universe.yaml")


def load_events(path: Path | None = None) -> dict:
    return _load(path or CONFIG_DIR / "events.yaml")


def load_watch(path: Path | None = None) -> dict:
    return _load(path or CONFIG_DIR / "watch.yaml")
