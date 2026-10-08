import json
import re

import pandas as pd

from spot_trd import journal
from spot_trd.config import load_rules, load_universe
from spot_trd.dashboard import build_context, decision_kind, render
from spot_trd.watch import Alert
from tests.helpers import make_feat

RULES, U = load_rules(), load_universe()
NOW = pd.Timestamp("2026-10-01 12:00")
NO_EVENTS = {"block_window_days": 1, "fomc_decisions": ["2026-10-28"], "cpi_releases": ["2026-10-14"]}
TICKER = {"last": 105_000.0, "timestamp": 1_790_000_000_000, "percentage": -1.5}


def book(tmp_path):
    p = tmp_path / "j.csv"
    journal.main(["deposit", "25"], path=p)
    return journal.load_book(RULES, p)


def h4():
    idx = pd.date_range("2026-10-01", periods=3, freq="4h")
    return pd.DataFrame({"open": 1.0e5, "high": 1.06e5, "low": 0.99e5, "close": 1.05e5, "volume": 1.0}, index=idx)


def test_decision_kinds():
    assert decision_kind("NO ACTION. Stay in USDT.") == "neutral"
    assert decision_kind("PLACE 2 LIMIT BUY ORDERS NOW") == "buy"
    assert decision_kind("HOLD. Move your stop") == "hold"
    assert decision_kind("SELL ALL BTC AT MARKET NOW") == "sell"
    assert decision_kind("NO DECISION: data problem") == "problem"


def test_no_action_page(tmp_path):
    ctx = build_context(make_feat(signal=False), book(tmp_path), RULES, U, NO_EVENTS, TICKER, h4(), [], True, NOW)
    page = render(ctx)
    assert "NO ACTION" in page and "No alerts" in page
    assert ctx["focus"][0] == "Move to setup trigger" and ctx["focus"][1] < 0  # same sign as the levels table
    assert ctx["next_event"] == "CPI 2026-10-14"
    assert ctx["chart"]["forming"]["close"] == 105_000.0
    data = json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>', page, re.S).group(1))
    assert data["chart"]["price_lines"][0]["title"] == "Setup trigger"


def test_buy_page_lists_orders_and_stop(tmp_path):
    ctx = build_context(make_feat(), book(tmp_path), RULES, U, NO_EVENTS, TICKER, h4(), [], True, NOW)
    assert ctx["kind"] == "buy"
    assert any(s.startswith("Limit buy 1") for s in ctx["steps"])
    assert any("stop-market trigger" in s for s in ctx["steps"])
    assert {l["title"] for l in ctx["chart"]["price_lines"]} >= {"Limit buy 1", "Stop if filled"}


def test_alerts_and_data_issue_render_escaped(tmp_path):
    alerts = [Alert("stop-near:T1:x", "Price <near> stop", "check & act")]
    ctx = build_context(make_feat(signal=False), book(tmp_path), RULES, U, NO_EVENTS, TICKER, h4(), alerts, True, NOW,
                        data_issues=["BTC data fresh: stale"])
    page = render(ctx)
    assert ctx["kind"] == "problem"
    assert "Price &lt;near&gt; stop" in page and "check &amp; act" in page
    assert "BTC data fresh: stale" in page


def test_page_works_without_live_feed(tmp_path):
    ctx = build_context(make_feat(signal=False), book(tmp_path), RULES, U, NO_EVENTS, None, None, [], True, NOW)
    assert ctx["live_time"] == "unavailable" and ctx["chart"]["forming"] is None
    assert "<html" in render(ctx)
