"""Local HTML dashboard, rewritten by the monitor on every check. Open dashboard/index.html in a browser."""
import html
import json
import os

import pandas as pd

from spot_trd.clock import label as tz_label, local, local_hm, offset_hours
from spot_trd.config import ROOT
from spot_trd.journal import Book
from spot_trd.run import build_card, trailing_stop

DASH_DIR = ROOT / "dashboard"
DASH_FILE = DASH_DIR / "index.html"
REFRESH_SECONDS = 120
CHART_JS = "https://unpkg.com/lightweight-charts@4.2.3/dist/lightweight-charts.standalone.production.js"

STATUS = {  # (css role, icon, label); icon + label so state never relies on color alone
    "neutral": ("neutral", "●", "No action"),
    "buy": ("good", "▲", "Place buy orders"),
    "hold": ("warning", "◆", "Update your stop"),
    "keep": ("warning", "◆", "Buy orders resting"),
    "sell": ("critical", "▼", "Sell / check now"),
    "problem": ("critical", "!", "Attention"),
}
ALERT_ROLE = {"stop-breach": "critical", "stop-near": "warning", "limit-touch": "warning",
              "expiry": "warning", "setup-near": "neutral"}


def decision_kind(headline: str) -> str:
    for prefix, kind in (("NO ACTION", "neutral"), ("PLACE", "buy"), ("HOLD", "hold"), ("KEEP", "keep"),
                         ("SELL", "sell"), ("CHECK", "sell")):
        if headline.startswith(prefix):
            return kind
    return "problem"


def _pct(a: float, b: float) -> float:
    return a / b - 1


def build_context(feat: pd.DataFrame, book: Book, rules: dict, universe: dict, events: dict, ticker: dict | None,
                  h4: pd.DataFrame | None, alerts: list, paper: bool, now: pd.Timestamp,
                  data_issues: list[str] | None = None, run_at: str = "00:05") -> dict:
    last = feat.iloc[-1]
    card_text, new_plan = build_card(feat, book, rules, universe, events, now)
    headline = next(l for l in card_text.splitlines() if l.startswith(">>> TODAY:")).removeprefix(">>> TODAY: ")
    if data_issues:
        headline = "NO DECISION: data problem. Do nothing until it clears; the monitor keeps retrying."
    live = ticker["last"] if ticker else float(last["close"])
    offset = rules["exit"]["stop_limit_offset"]

    levels = [("EMA20", last["ema_pb"]), ("EMA50", last["ema_fast"]), ("EMA200", last["ema_slow"])]
    price_lines, steps = [], []
    trade, active = book.open_trade, book.active_plan(now)
    equity = book.cash + (trade.held * live if trade else 0.0)
    focus = None
    if trade:
        stop, _ = trailing_stop(feat, trade, rules)
        price_lines.append({"price": stop, "role": "critical", "title": "Stop"})
        levels.append(("Your stop (trigger)", stop))
        steps.append(f"Stop-market sell for {trade.held:.5f} BTC: trigger {stop:,.2f} "
                     f"(if only Stop-Limit is offered: limit {stop * (1 - offset):,.2f})")
        focus = ("Move to your stop", _pct(stop, live), f"stop {stop:,.0f}")
    plan_orders, plan_stop, plan_until = None, None, None
    if new_plan:
        plan, plan_until = new_plan
        plan_orders, plan_stop = [(o.price, o.qty) for o in plan.orders], plan.stop
    elif active and active.btc_bought == 0:
        plan_orders, plan_stop, plan_until = active.plan["orders"], active.plan["stop"], pd.Timestamp(active.plan["valid_until"])
    if plan_orders:
        for i, (p, q) in enumerate(plan_orders, 1):
            price_lines.append({"price": p, "role": "warning", "title": f"Limit buy {i}"})
            levels.append((f"Limit buy {i}", p))
            steps.append(f"Limit buy {i}: price {p:,.2f}, amount {q:.5f} BTC (~{p * q:.2f} USDT)")
        price_lines.append({"price": plan_stop, "role": "critical", "title": "Stop if filled"})
        levels.append(("Stop once filled", plan_stop))
        steps.append(f"Once filled: stop-market trigger {plan_stop:,.2f} "
                     f"(if only Stop-Limit is offered: limit {plan_stop * (1 - offset):,.2f})")
        steps.append(f"Cancel unfilled orders at {local(plan_until)}")
        if focus is None:
            top = max(p for p, _ in plan_orders)
            focus = ("Move to your limit buy", _pct(top, live), f"limit {top:,.0f}")
    trigger = last["ema_pb"] * (1 + rules["setup"]["pullback_tolerance"])
    if trade is None and not plan_orders and last["regime_ok"]:
        price_lines.append({"price": trigger, "role": "good", "title": "Setup trigger"})
        levels.append(("Setup trigger (daily close <=)", trigger))
        focus = ("Move to setup trigger", _pct(trigger, live), f"daily close <= {trigger:,.0f}, RSI < {rules['setup']['rsi_max']}")
    if focus is None:
        focus = ("Setup trigger", None, "gates closed: no setup can form")

    upcoming = []
    for kind, label in (("fomc_decisions", "FOMC"), ("cpi_releases", "CPI")):
        upcoming += [(pd.Timestamp(d), label) for d in events.get(kind, []) if pd.Timestamp(d) >= now.normalize()]
    upcoming.sort()

    daily = feat.iloc[-180:]
    candles = [{"time": d.strftime("%Y-%m-%d"), "open": r.open, "high": r.high, "low": r.low, "close": r.close}
               for d, r in daily.iterrows()]
    forming = None
    if h4 is not None and ticker:
        today = h4[h4.index >= now.normalize()]
        if len(today):
            forming = {"time": now.strftime("%Y-%m-%d"), "open": float(today["open"].iloc[0]),
                       "high": max(float(today["high"].max()), live), "low": min(float(today["low"].min()), live),
                       "close": live}
    ema = {name: [{"time": d.strftime("%Y-%m-%d"), "value": float(v)} for d, v in daily[col].items()]
           for name, col in (("EMA20", "ema_pb"), ("EMA50", "ema_fast"), ("EMA200", "ema_slow"))}
    setups = [d.strftime("%Y-%m-%d") for d in daily.index[daily["signal"]]]
    h4_candles = [] if h4 is None else [
        {"time": int(ts.timestamp() + offset_hours() * 3600), "open": r.open, "high": r.high, "low": r.low, "close": r.close}
        for ts, r in h4.iterrows()]

    closed = [{"id": t.trade_id, "entry": str(t.first_buy.date()), "exit": str(t.closed_at.date()),
               "pnl": t.pnl, "r": t.pnl / t.risk_usdt(rules)} for t in book.closed_trades][-10:]
    breaker = book.breaker
    run_h, run_m = map(int, run_at.split(":"))
    next_card = now.normalize() + pd.Timedelta(hours=run_h, minutes=run_m)
    if next_card <= now:
        next_card += pd.Timedelta(days=1)

    return {
        "generated_at": now.isoformat() + "Z",
        "next_card_at": next_card.isoformat() + "Z",
        "mode": "PAPER" if paper else "LIVE",
        "headline": headline,
        "kind": decision_kind(headline),
        "steps": steps,
        "alerts": [{"title": a.title, "message": a.message, "role": ALERT_ROLE.get(a.key.split(":")[0], "warning")}
                   for a in alerts],
        "data_issues": data_issues or [],
        "live": live,
        "live_change": ticker["percentage"] if ticker else None,
        "live_time": local_hm(pd.Timestamp(ticker["timestamp"], unit="ms")) if ticker else "unavailable",
        "equity": equity,
        "deposited": book.deposited,
        "cash": book.cash,
        "focus": focus,
        "rsi": float(last["rsi"]),
        "rsi_max": rules["setup"]["rsi_max"],
        "atr_pct": float(last["atr"] / last["close"]),
        "close_date": str(last.name.date()),
        "gates": [
            ("1M uptrend", bool(last["monthly_up"]), "price above its 10-month average"),
            ("1D uptrend", bool(last["daily_up"]), "close > EMA200 and EMA50 > EMA200"),
            ("Macro calm", not bool(last["risk_off"]),
             "S&P above 50-day avg, no DXY surge, no gold+oil stress"),
        ],
        "next_event": f"{upcoming[0][1]} {upcoming[0][0]:%Y-%m-%d}" if upcoming else "none in calendar",
        "levels": sorted(((n, float(p), _pct(float(p), live)) for n, p in levels), key=lambda x: -x[1]),
        "trade": None if trade is None else {"id": trade.trade_id, "btc": trade.held, "entry": trade.avg_entry,
                                             "pnl_pct": _pct(live, trade.avg_entry / (1 + rules["market"]["fee_rate"]))},
        "closed": closed,
        "breaker": (f"Paused until {breaker.halt_until.date()}" if breaker and breaker.halted(now)
                    else "Active (not tripped)"),
        "risk_pct": (rules["risk"]["small_account"]["risk_pct"]
                     if book.cash < rules["risk"]["small_account"]["below_equity"] else rules["risk"]["risk_pct"]),
        "card_text": card_text,
        "chart": {"candles": candles, "forming": forming, "ema": ema, "setups": setups,
                  "price_lines": price_lines, "h4": h4_candles},
    }


def _e(x) -> str:
    return html.escape(str(x))


def _tile(label: str, value: str, sub: str = "", delta: float | None = None) -> str:
    d = ""
    if delta is not None and abs(delta) < 5e-5:
        d = '<span class="delta">0.00%</span>'
    elif delta is not None:
        cls, arrow = ("up", "▲") if delta > 0 else ("down", "▼")
        d = f'<span class="delta {cls}">{arrow} {abs(delta):.2%}</span>'
    return (f'<div class="tile"><div class="tile-label">{_e(label)}</div><div class="tile-value">{_e(value)}</div>'
            f'<div class="tile-sub">{d} {_e(sub)}</div></div>')


def render(ctx: dict) -> str:
    role, icon, label = STATUS[ctx["kind"]]
    steps = "".join(f"<li>{_e(s)}</li>" for s in ctx["steps"])
    alerts = "".join(
        f'<li class="alert {a["role"]}"><span class="chip {a["role"]}">{"!" if a["role"] == "critical" else "◆" if a["role"] == "warning" else "●"}</span>'
        f'<div><strong>{_e(a["title"])}</strong><br><span class="muted">{_e(a["message"])}</span></div></li>'
        for a in ctx["alerts"]) or '<li class="alert neutral"><span class="chip neutral">●</span><div>No alerts. Nothing needs your attention right now.</div></li>'
    issues = "".join(f'<li class="alert critical"><span class="chip critical">!</span><div>{_e(i)}</div></li>'
                     for i in ctx["data_issues"])
    focus_label, focus_pct, focus_sub = ctx["focus"]
    tiles = "".join([
        _tile("BTC live", f"{ctx['live']:,.0f}", f"24h · {ctx['live_time']}",
              None if ctx["live_change"] is None else ctx["live_change"] / 100),
        _tile("Equity (USDT)", f"{ctx['equity']:,.2f}", f"since start · deposited {ctx['deposited']:,.2f}",
              _pct(ctx["equity"], ctx["deposited"]) if ctx["deposited"] else None),
        _tile(focus_label, "—" if focus_pct is None else f"{focus_pct:+.1%}", focus_sub),
        _tile("RSI (14, daily)", f"{ctx['rsi']:.0f}", f"setup needs < {ctx['rsi_max']}"),
        _tile("Volatility (ATR)", f"{ctx['atr_pct']:.1%}", "typical daily range"),
    ])
    gates = "".join(
        f'<li><span class="chip {"good" if ok else "critical"}">{"✓" if ok else "✗"}</span>'
        f'<div><strong>{_e(name)}: {"yes" if ok else "no"}</strong><br><span class="muted">{_e(why)}</span></div></li>'
        for name, ok, why in ctx["gates"])
    levels = "".join(f"<tr><td>{_e(n)}</td><td class='num'>{p:,.2f}</td><td class='num'>{d:+.1%}</td></tr>"
                     for n, p, d in ctx["levels"])
    trade = ctx["trade"]
    position = ("No open position. All capital in USDT." if trade is None else
                f"{trade['id']}: {trade['btc']:.5f} BTC, avg entry {trade['entry']:,.2f}, now {trade['pnl_pct']:+.1%}")
    closed = "".join(f"<tr><td>{_e(c['id'])}</td><td>{c['entry']}</td><td>{c['exit']}</td>"
                     f"<td class='num'>{c['pnl']:+.2f}</td><td class='num'>{c['r']:+.2f}R</td></tr>"
                     for c in ctx["closed"]) or "<tr><td colspan='5' class='muted'>No closed trades yet.</td></tr>"
    data = json.dumps({k: ctx[k] for k in ("chart", "generated_at", "next_card_at")}).replace("</", "<\\/")

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="{REFRESH_SECONDS}">
<title>BTC Decision Board</title>
<style>
:root {{
  color-scheme: light;
  --page: #f9f9f7; --surface-1: #fcfcfb; --ink-1: #0b0b0b; --ink-2: #52514e; --muted: #898781;
  --grid: #e1e0d9; --axis: #c3c2b7; --border: rgba(11,11,11,0.10);
  --s1: #2a78d6; --s2: #eb6834; --s3: #1baf7a;
  --good: #0ca30c; --warning: #fab219; --serious: #ec835a; --critical: #d03b3b; --neutral: #898781;
  --up-text: #006300; --down-text: #d03b3b;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    color-scheme: dark;
    --page: #0d0d0d; --surface-1: #1a1a19; --ink-1: #ffffff; --ink-2: #c3c2b7; --muted: #898781;
    --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10);
    --s1: #3987e5; --s2: #d95926; --s3: #199e70; --up-text: #0ca30c; --down-text: #e66767;
  }}
}}
:root[data-theme="dark"] {{
  color-scheme: dark;
  --page: #0d0d0d; --surface-1: #1a1a19; --ink-1: #ffffff; --ink-2: #c3c2b7; --muted: #898781;
  --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10);
  --s1: #3987e5; --s2: #d95926; --s3: #199e70; --up-text: #0ca30c; --down-text: #e66767;
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--page); color: var(--ink-1);
  font: 15px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif; }}
main {{ max-width: 1180px; margin: 0 auto; padding: 20px 16px 48px; }}
header {{ display: flex; flex-wrap: wrap; gap: 8px 16px; align-items: baseline; justify-content: space-between; }}
h1 {{ font-size: 20px; margin: 0; }}
h2 {{ font-size: 14px; text-transform: uppercase; letter-spacing: .04em; color: var(--ink-2); margin: 0 0 10px; }}
.muted {{ color: var(--ink-2); }}
.small {{ font-size: 13px; }}
.badge {{ font-size: 12px; font-weight: 700; padding: 2px 8px; border-radius: 999px; border: 1px solid var(--border); }}
.card {{ background: var(--surface-1); border: 1px solid var(--border); border-radius: 12px; padding: 16px; margin-top: 16px; }}
.hero {{ border-left: 6px solid var(--neutral); }}
.hero.good {{ border-left-color: var(--good); }} .hero.warning {{ border-left-color: var(--warning); }}
.hero.critical {{ border-left-color: var(--critical); }}
.hero-label {{ display: flex; gap: 8px; align-items: center; font-weight: 700; color: var(--ink-2); }}
.hero-text {{ font-size: 22px; font-weight: 650; margin: 8px 0 4px; }}
.hero ol {{ margin: 8px 0 0; padding-left: 20px; }}
.chip {{ display: inline-flex; width: 22px; height: 22px; border-radius: 50%; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 700; color: #fff; flex: none; background: var(--neutral); }}
.chip.good {{ background: var(--good); }} .chip.warning {{ background: var(--warning); color: #0b0b0b; }}
.chip.critical {{ background: var(--critical); }}
ul.list {{ list-style: none; margin: 0; padding: 0; display: grid; gap: 10px; }}
ul.list li {{ display: flex; gap: 10px; align-items: flex-start; }}
.tiles {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin-top: 16px; }}
.tile {{ background: var(--surface-1); border: 1px solid var(--border); border-radius: 12px; padding: 14px; }}
.tile-label {{ font-size: 13px; color: var(--ink-2); }}
.tile-value {{ font-size: 28px; font-weight: 650; margin-top: 2px; }}
.tile-sub {{ font-size: 12px; color: var(--muted); }}
.delta.up {{ color: var(--up-text); font-weight: 600; }} .delta.down {{ color: var(--down-text); font-weight: 600; }}
.grid2 {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; }}
.grid2 > .card {{ margin-top: 0; }}
.legend {{ display: flex; flex-wrap: wrap; gap: 6px 14px; font-size: 12px; color: var(--ink-2); margin-bottom: 8px; }}
.sw {{ display: inline-block; width: 14px; height: 3px; border-radius: 2px; vertical-align: middle; margin-right: 4px; }}
.hover {{ font-size: 12px; color: var(--ink-2); min-height: 18px; font-variant-numeric: tabular-nums; }}
.chart {{ width: 100%; height: 380px; }}
.chart.small {{ height: 260px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
th, td {{ text-align: left; padding: 6px 4px; border-bottom: 1px solid var(--grid); }}
th {{ color: var(--ink-2); font-weight: 600; font-size: 12px; }}
td.num, th.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
pre {{ white-space: pre-wrap; font-size: 12px; color: var(--ink-2); }}
#stale {{ display: none; background: var(--critical); color: #fff; padding: 10px 14px; border-radius: 10px; margin-top: 12px; font-weight: 600; }}
footer {{ margin-top: 24px; font-size: 12px; color: var(--muted); }}
</style>
</head>
<body>
<main>
<header>
  <h1>BTC/USDT decision board <span class="badge">{ctx['mode']}</span></h1>
  <div class="small muted">Updated <span id="age">just now</span> · next daily card <span id="next">{local_hm("2000-01-01 00:05")}</span> · page reloads every {REFRESH_SECONDS // 60} min</div>
</header>
<div id="stale">This page hasn't been updated for over 12 minutes. Is the monitor running? Run <code>uv run spot start</code>.</div>

<section class="card hero {role}">
  <div class="hero-label"><span class="chip {role}">{icon}</span> TODAY · {_e(label)}</div>
  <div class="hero-text">{_e(ctx['headline'])}</div>
  {f'<ol>{steps}</ol>' if steps else ''}
  <div class="small muted" style="margin-top:8px">Decision from the {ctx['close_date']} daily close. Live prices below are context; act on this line.</div>
</section>

<section class="card"><h2>Alerts</h2><ul class="list">{issues}{alerts}</ul></section>

<div class="tiles">{tiles}</div>

<section class="card">
  <h2>Daily chart (last 180 days + today forming)</h2>
  <div class="legend">
    <span><span class="sw" style="background:var(--s1)"></span>EMA20</span>
    <span><span class="sw" style="background:var(--s2)"></span>EMA50</span>
    <span><span class="sw" style="background:var(--s3)"></span>EMA200</span>
    <span>□ up day · ■ down day</span><span>▲ past buy setup</span><span>dashed lines: your levels (labelled on the right)</span>
  </div>
  <div class="hover" id="hover-d"></div>
  <div class="chart" id="chart-d"></div>
</section>

<div class="grid2" style="margin-top:16px">
  <section class="card"><h2>4H chart (last 10 days)</h2><div class="hover" id="hover-h"></div><div class="chart small" id="chart-h"></div></section>
  <section class="card"><h2>Key levels vs live price</h2>
    <table><thead><tr><th>Level</th><th class="num">Price</th><th class="num">vs live</th></tr></thead><tbody>{levels}</tbody></table>
  </section>
</div>

<div class="grid2" style="margin-top:16px">
  <section class="card"><h2>Gates (all must be ✓ to buy)</h2><ul class="list">{gates}</ul>
    <p class="small muted" style="margin-bottom:0">Next high-volatility event: {_e(ctx['next_event'])} (no new entries on or the day before).</p></section>
  <section class="card"><h2>Account</h2>
    <p style="margin-top:0">{_e(position)}</p>
    <p class="small muted">Cash {ctx['cash']:,.2f} USDT · risk per trade {ctx['risk_pct']:.0%} · circuit breaker: {_e(ctx['breaker'])}</p>
    <table><thead><tr><th>Trade</th><th>Entry</th><th>Exit</th><th class="num">P&amp;L</th><th class="num">R</th></tr></thead><tbody>{closed}</tbody></table>
  </section>
</div>

<section class="card"><details><summary>Full card text</summary><pre>{_e(ctx['card_text'])}</pre></details></section>

<footer>Halal: BTC/USDT spot only. No margin, no shorting, no interest products. Decisions use completed daily candles; the monitor checks live prices every 5 minutes.
Stop the monitor with <code>uv run spot stop</code>.</footer>
</main>

<script id="data" type="application/json">{data}</script>
<script src="{CHART_JS}"></script>
<script>
(function () {{
  const D = JSON.parse(document.getElementById('data').textContent);
  const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const fmt = n => n.toLocaleString(undefined, {{maximumFractionDigits: 0}});

  function tick() {{
    const age = (Date.now() - Date.parse(D.generated_at)) / 60000;
    document.getElementById('age').textContent = age < 1 ? 'just now' : Math.round(age) + ' min ago';
    document.getElementById('stale').style.display = age > 12 ? 'block' : 'none';
    const next = (Date.parse(D.next_card_at) - Date.now()) / 60000;
    document.getElementById('next').textContent = next > 0 ? 'in ' + Math.floor(next / 60) + 'h ' + Math.round(next % 60) + 'm' : 'due now';
  }}
  tick(); setInterval(tick, 30000);

  if (!window.LightweightCharts) {{
    for (const id of ['chart-d', 'chart-h']) document.getElementById(id).textContent = 'Chart library could not load (offline?). Levels table and decision are still valid.';
    return;
  }}
  const base = () => ({{
    layout: {{ background: {{ type: 'solid', color: css('--surface-1') }}, textColor: css('--ink-2'),
              fontFamily: 'system-ui, -apple-system, "Segoe UI", sans-serif' }},
    grid: {{ vertLines: {{ color: css('--grid') }}, horzLines: {{ color: css('--grid') }} }},
    rightPriceScale: {{ borderColor: css('--axis') }},
    timeScale: {{ borderColor: css('--axis') }},
    crosshair: {{ mode: 0 }},
  }});
  const candleStyle = () => ({{
    upColor: css('--surface-1'), borderUpColor: css('--ink-1'), wickUpColor: css('--ink-1'),
    downColor: css('--ink-2'), borderDownColor: css('--ink-2'), wickDownColor: css('--ink-2'),
    priceLineVisible: false, priceFormat: {{ type: 'price', precision: 0, minMove: 1 }},
  }});

  function mount(id, hoverId, timeVisible) {{
    const el = document.getElementById(id);
    const chart = LightweightCharts.createChart(el, {{ ...base(), width: el.clientWidth, height: el.clientHeight,
      timeScale: {{ borderColor: css('--axis'), timeVisible }} }});
    new ResizeObserver(() => chart.applyOptions({{ width: el.clientWidth }})).observe(el);
    const key = 'range-' + id;
    try {{ const r = JSON.parse(sessionStorage.getItem(key)); if (r) setTimeout(() => chart.timeScale().setVisibleLogicalRange(r), 0); }} catch (e) {{}}
    chart.timeScale().subscribeVisibleLogicalRangeChange(r => {{ try {{ sessionStorage.setItem(key, JSON.stringify(r)); }} catch (e) {{}} }});
    return chart;
  }}

  function hover(chart, series, hoverId, extra) {{
    const out = document.getElementById(hoverId);
    const show = (bar, label, more) => {{
      if (!bar) return;
      out.textContent = label + '  O ' + fmt(bar.open) + '  H ' + fmt(bar.high) + '  L ' + fmt(bar.low) + '  C ' + fmt(bar.close) + (more || '');
    }};
    chart.subscribeCrosshairMove(p => {{
      if (!p.time || !p.seriesData) return;
      const bar = p.seriesData.get(series);
      let more = '';
      for (const [name, s] of extra) {{ const v = p.seriesData.get(s); if (v) more += '  ' + name + ' ' + fmt(v.value); }}
      show(bar, typeof p.time === 'string' ? p.time : new Date(p.time * 1000).toISOString().slice(5, 16).replace('T', ' ') + ' {tz_label()}', more);
    }});
    return show;
  }}

  // Daily chart
  const dc = mount('chart-d', 'hover-d', false);
  const candles = dc.addCandlestickSeries(candleStyle());
  const bars = D.chart.candles.slice();
  if (D.chart.forming) bars.push(D.chart.forming);
  candles.setData(bars);
  const emaSeries = [];
  [['EMA20', '--s1'], ['EMA50', '--s2'], ['EMA200', '--s3']].forEach(([name, color]) => {{
    const s = dc.addLineSeries({{ color: css(color), lineWidth: 2, title: name, priceLineVisible: false,
                                  crosshairMarkerRadius: 4, priceFormat: {{ type: 'price', precision: 0, minMove: 1 }} }});
    s.setData(D.chart.ema[name]);
    emaSeries.push([name, s]);
  }});
  for (const l of D.chart.price_lines) {{
    candles.createPriceLine({{ price: l.price, color: css('--' + l.role), lineWidth: 1, lineStyle: 2,
                              axisLabelVisible: true, title: l.title }});
  }}
  candles.setMarkers(D.chart.setups.map(t => ({{ time: t, position: 'belowBar', color: css('--good'), shape: 'arrowUp' }})));
  const showD = hover(dc, candles, 'hover-d', emaSeries);
  const lastD = bars[bars.length - 1];
  showD(lastD, lastD.time + (D.chart.forming ? ' (forming)' : ''));
  if (!sessionStorage.getItem('range-chart-d')) dc.timeScale().fitContent();

  // 4H chart
  if (D.chart.h4.length) {{
    const hc = mount('chart-h', 'hover-h', true);
    const h4 = hc.addCandlestickSeries(candleStyle());
    h4.setData(D.chart.h4);
    for (const l of D.chart.price_lines) {{
      h4.createPriceLine({{ price: l.price, color: css('--' + l.role), lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: l.title }});
    }}
    const showH = hover(hc, h4, 'hover-h', []);
    const lastH = D.chart.h4[D.chart.h4.length - 1];
    showH(lastH, 'latest 4H');
    if (!sessionStorage.getItem('range-chart-h')) hc.timeScale().fitContent();
  }}
}})();
</script>
</body>
</html>
"""


def write_dashboard(ctx: dict) -> str:
    DASH_DIR.mkdir(parents=True, exist_ok=True)
    tmp = DASH_FILE.with_suffix(".tmp")
    tmp.write_text(render(ctx), encoding="utf-8")
    os.replace(tmp, DASH_FILE)  # atomic swap so the browser never loads a half-written page
    return str(DASH_FILE)
