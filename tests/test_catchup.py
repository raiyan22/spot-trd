import csv

import pandas as pd
import pytest

from spot_trd import catchup, decisions, journal, watch
from spot_trd.config import load_rules, load_universe
from spot_trd.run import build_card
from tests.helpers import make_feat

RULES, U = load_rules(), load_universe()
NO_EVENTS = {"block_window_days": 1, "fomc_decisions": [], "cpi_releases": []}


@pytest.fixture
def env(tmp_path, monkeypatch):
    log = tmp_path / "decisions.csv"
    monkeypatch.setattr(decisions, "LOG_LIVE", log)
    with open(log, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=decisions.FIELDS)
        w.writeheader()
        w.writerow({"card_day": "2026-09-28"})  # last card the app made: close of 09-27
    jpath = tmp_path / "j.csv"
    journal.main(["deposit", "25"], path=jpath)
    return jpath, log


def run(jpath, now, monkeypatch, feat=None):
    monkeypatch.setattr(catchup, "utcnow", lambda: pd.Timestamp(now))
    return catchup.catch_up(feat if feat is not None else make_feat(), RULES, U, NO_EVENTS, jpath, paper=False)


def test_missed_closes_exclude_the_latest_close():
    f = make_feat()
    missed = catchup.missed_closes(f, pd.Timestamp("2026-09-28"))
    assert [str(d.date()) for d in missed] == ["2026-09-28", "2026-09-29"]
    assert not len(catchup.missed_closes(f, None))  # first run: nothing missed


def test_missed_plan_still_valid_is_recorded(env, monkeypatch):
    jpath, log = env
    lines = run(jpath, "2026-09-30 12:00", monkeypatch)
    assert lines[0].startswith(catchup.HEADER)
    assert "plan T001 recorded" in lines[1] and "KEEP" in lines[2]
    book = journal.load_book(RULES, jpath)
    assert book.active_plan(pd.Timestamp("2026-09-30 12:00")).trade_id == "T001"
    with open(log, newline="", encoding="utf-8") as f:
        assert [r["card_day"] for r in csv.DictReader(f)] == ["2026-09-28", "2026-09-29", "2026-09-30"]


def test_expired_missed_plan_is_reported_not_recorded(env, monkeypatch):
    jpath, _ = env
    lines = run(jpath, "2026-10-08 12:00", monkeypatch)
    assert all("expired" in l for l in lines[1:])
    assert not journal.load_book(RULES, jpath).trades


def test_nothing_missed_means_no_report(env, monkeypatch):
    jpath, _ = env
    f = make_feat(n=30)
    assert run(jpath, "2026-09-30 12:00", monkeypatch, feat=f.loc[:"2026-09-28"]) == []


def test_trend_break_on_a_missed_day_still_says_sell(tmp_path):
    jpath = tmp_path / "j.csv"
    journal.main(["deposit", "25"], path=jpath)
    f = make_feat()
    now = pd.Timestamp("2026-10-01 01:00")
    _, (plan, valid_until) = build_card(f, journal.load_book(RULES, jpath), RULES, U, NO_EVENTS, now)
    journal.record_plan(plan, RULES, jpath, valid_until=valid_until)
    o = plan.orders[0]
    journal.main(["buy", "--usdt", f"{o.notional:.4f}", "--btc", f"{o.qty}", "--time", "2026-09-20T00:00:00"], path=jpath)
    f.loc[pd.Timestamp("2026-09-25"), "trend_ok"] = False  # broke, then recovered by the last close
    text, _ = build_card(f, journal.load_book(RULES, jpath), RULES, U, NO_EVENTS, now)
    assert ">>> TODAY: SELL ALL BTC AT MARKET NOW" in text and "2026-09-25" in text


def test_brief_shows_decision_steps_and_alerts():
    status = {"generated_at": "2026-10-08T09:00:00Z", "next_card_at": "2026-10-09T00:05:00Z", "mode": "PAPER",
              "headline": "PLACE 2 LIMIT BUY ORDERS NOW", "kind": "buy", "steps": ["Limit buy 1: price 80,000.00"],
              "alerts": [{"title": "BUY may have filled", "message": "check Binance", "role": "warning"}],
              "data_issues": [], "live": 81000.0, "live_change": 1.5, "equity": 300.0,
              "focus": ["Move to your limit buy", -0.012, "limit 80,000"]}
    text = watch.format_brief(status, running=True)
    for part in ("monitor RUNNING", "TODAY: PLACE 2", "Limit buy 1", "BTC 81,000", "BUY may have filled", "-1.2%"):
        assert part in text
    assert "No status yet" in watch.format_brief(None)


def test_cloud_notifies_only_when_there_is_something_to_do(monkeypatch):
    from spot_trd import cloud, run as run_mod

    sent = []
    monkeypatch.setattr(cloud, "notify", lambda key, title, body: sent.append(title))
    for headline in ("NO ACTION. Stay in USDT.", "PLACE 2 LIMIT BUY ORDERS NOW (below)."):
        monkeypatch.setattr(run_mod, "produce_card", lambda *a, h=headline, **k: (f"x\n>>> TODAY: {h}\n", True))
        cloud.daily()
    assert len(sent) == 1 and "PLACE 2" in sent[0]
