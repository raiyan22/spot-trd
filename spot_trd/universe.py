"""Does a small, Sharia-screened asset universe improve the economics? (v3 research, nothing here is live.)

Same v2 rules and parameters on every asset; one shared account; a hard cap on concurrent positions; total portfolio risk
held at the single-asset budget. Assets are served in a fixed order chosen before any result was seen.
Run: uv run python -m spot_trd.universe
"""
import copy
import json
from datetime import date

import numpy as np
import pandas as pd

from spot_trd.audit import economics, load_asset, pct, table
from spot_trd.backtest import Result, run_portfolio
from spot_trd.config import RAW_DIR, REPORTS_DIR, load_rules, load_universe
from spot_trd.data import load_data, market_limits
from spot_trd.regime import build_features
from spot_trd.report import max_drawdown

# Priority order = the order the user listed them (BTC, ETH, SOL, ADA) plus a fifth chosen on screening criteria
# (oldest non-smart-contract payment coin, no DeFi/meme ecosystem), NOT on backtest results. Fixed before the run.
ORDER = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "ADA/USDT", "LTC/USDT"]
COMBOS = {"BTC": 1, "BTC+ETH": 2, "BTC+ETH+SOL": 3, "BTC+ETH+SOL+ADA": 4, "BTC+ETH+SOL+ADA+LTC": 5}
EDGE_CAPITAL, EDGE_RISK = 100_000.0, 0.02
CAPITALS = (25.0, 100.0, 300.0)

# Materiality tests, fixed before running. A universe "materially improves" only if ALL hold versus BTC-only
# (same window, same position cap, same fills):
CRITERIA = [
    ("M1 opportunity", "trades per year at least 1.5x BTC-only"),
    ("M2 dollar return", "edge-test annualized return at least 1.25x BTC-only, and still positive under harsh fills"),
    ("M3 risk", "max drawdown no more than 25% deeper than BTC-only, and longest losing streak no more than 2 trades longer"),
    ("M4 consistency", "annualized return no worse than BTC-only in BOTH halves of the window"),
]


def asset_limits() -> dict:
    path = RAW_DIR / "asset_limits.json"
    if path.exists():
        return json.loads(path.read_text())
    out = {}
    for sym in ORDER:
        m = market_limits(sym)
        out[sym] = {"min_notional": m["min_notional"], "qty_step": m["qty_step"]}
    path.write_text(json.dumps(out, indent=1))
    return out


def harsh(base: dict) -> dict:
    r = copy.deepcopy(base)
    r["execution"] = {"limit_penetration": 0.0015, "exit_at_next_open": True, "exit_slippage": 0.003}
    r["exit"]["stop_slippage"] = 0.005
    return r


def slice_from(feats: dict[str, pd.DataFrame], start: pd.Timestamp) -> dict[str, pd.DataFrame]:
    return {k: v[v.index >= start] for k, v in feats.items()}


def run(feats, rules, universe, limits, n_assets, k, capital, risk, alloc="equal") -> Result:
    syms = ORDER[:n_assets]
    return run_portfolio({s: feats[s] for s in syms}, rules, universe, capital, risk, max_positions=k,
                         allocation=alloc, asset_rules=limits)


def stats(res: Result, signals_per_year=None) -> dict:
    e = economics(res)
    e["signals_pa"] = res.signals / e["years"]
    e["trades_pa"] = e["trades"] / e["years"]
    e["avg_open"] = float(res.open_positions[res.open_positions > 0].mean()) if (res.open_positions > 0).any() else 0.0
    e["max_open"] = int(res.open_positions.max())
    e["multi_days"] = float((res.open_positions >= 2).mean())
    e["blocked"] = res.skipped.get("no free position slot", 0)
    mid = res.equity.index[len(res.equity) // 2]
    e["h1"] = economics(res, None, mid)["cagr"]
    e["h2"] = economics(res, mid, None)["cagr"]
    return e


def verdict(base: dict, cand: dict, cand_harsh: dict) -> list[bool]:
    m1 = cand["trades_pa"] >= 1.5 * base["trades_pa"]
    m2 = cand["cagr"] >= 1.25 * base["cagr"] and cand_harsh["cagr"] > 0
    m3 = (cand["max_dd"] >= base["max_dd"] * 1.25) and (cand["losing_streak"] <= base["losing_streak"] + 2)
    m4 = cand["h1"] >= base["h1"] and cand["h2"] >= base["h2"]
    return [m1, m2, m3, m4]


def build_report() -> str:
    rules, universe0 = load_rules(), load_universe()
    universe = {**universe0, "allowed_symbols": ORDER}   # research only; the live universe file is untouched
    btc, macro = load_data()
    limits = asset_limits()
    feats = {}
    for sym in ORDER:
        raw = btc if sym == "BTC/USDT" else load_asset(sym)
        feats[sym] = build_features(raw, macro, rules)
    starts = {s: f.index[0] for s, f in feats.items()}
    common = max(starts.values())
    hr = harsh(rules)

    L = [f"# Small-universe study ({date.today()})", "",
         "Same v2 rules and parameters on every asset (nothing tuned per coin), one shared account, assets served in the fixed "
         f"order {', '.join(s.split('/')[0] for s in ORDER)}. Per-asset Binance minimum order and lot size are applied. "
         "Edge test = 100,000 USDT at 2% risk (so Binance's minimum doesn't bind); dollar columns use the real risk "
         "schedule. Base fills unless marked harsh.", "",
         "**Total risk is held constant.** The single-asset per-trade risk budget (2% of equity below 50 USDT, else 1%) is the "
         "budget for the WHOLE account. `equal`: each of the k position slots gets 1/k of it. `heat`: a new position gets "
         "whatever budget the open positions' stops have not already used. More assets therefore never mean more total risk "
         "at the moment of entry.", "",
         "Data starts (features available): " + ", ".join(f"{s.split('/')[0]} {d.date()}" for s, d in starts.items()) +
         f". All universes are compared on the common window starting {common.date()} so they see the same market.", "",
         "**Pre-registered materiality test** (fixed before any portfolio result was seen). A universe materially improves on "
         "BTC-only only if ALL hold, vs BTC-only on the same window with the same fills:", ""]
    L += [f"- {a}: {b}" for a, b in CRITERIA] + [""]

    # main grid on the common window
    cf = slice_from(feats, common)
    base_ref = stats(run(cf, rules, universe, limits, 1, 1, EDGE_CAPITAL, EDGE_RISK), None)
    base_ref_h = stats(run(cf, hr, universe, limits, 1, 1, EDGE_CAPITAL, EDGE_RISK), None)
    rows, verdicts, raw = [], {}, {}
    for name, n in COMBOS.items():
        for alloc in ("equal", "heat"):
            for k in range(1, min(3, n) + 1):
                if alloc == "heat" and k == 1:
                    continue
                e = stats(run(cf, rules, universe, limits, n, k, EDGE_CAPITAL, EDGE_RISK, alloc), None)
                eh = stats(run(cf, hr, universe, limits, n, k, EDGE_CAPITAL, EDGE_RISK, alloc), None)
                d = {}
                for cap in CAPITALS:
                    d[cap] = economics(run(cf, rules, universe, limits, n, k, cap, None, alloc))
                raw[(name, k, alloc)] = (e, eh, d)
                ok =verdict(base_ref, e, eh) if (name, k) != ("BTC", 1) else [None] * 4
                verdicts[(name, k, alloc)] = ok
                rows.append([name, k, alloc, f"{e['signals_pa']:.1f}", f"{e['trades_pa']:.1f}", f"{e['avg_R']:+.2f}",
                             pct(e["cagr"]), pct(e["max_dd"]), f"{e['cagr'] / max(abs(e['max_dd']), 0.01):.2f}",
                             f"{e['sharpe']:.2f}", e["losing_streak"], f"{e['avg_open']:.2f} / {e['max_open']}",
                             f"{e['multi_days']:.0%}", pct(eh["cagr"]),
                             "ref" if ok[0] is None else "".join("Y" if v else "n" for v in ok)])
    L += [f"## Edge test, common window {common.date()} to {feats['BTC/USDT'].index[-1].date()}", ""]
    L += table(["Universe", "Max pos.", "Alloc.", "Signals/yr", "Trades/yr", "Avg R", "CAGR", "Max DD", "CAGR/DD", "Sharpe",
                "Losing streak", "Open avg / max", "Days with 2+ open", "CAGR harsh", "M1-M4"], rows)

    # dollars
    L += ["## Dollar outcomes (real risk schedule, base fills, common window)", "",
          "Estimated profit per year in USDT. `-` = the position could never clear Binance's 5.50 USDT minimum, so the system "
          "would not trade.", ""]
    drows = []
    for (name, k, alloc), (e, eh, d) in raw.items():
        if alloc != "equal":
            continue
        cells = []
        for cap in CAPITALS:
            x = d[cap]
            cells.append(f"{x['profit_per_year']:+.2f} (DD {x['max_dd']:.1%}, {x['trades']} tr)" if x["trades"] else "-")
        drows.append([name, k] + cells)
    L += table(["Universe", "Max pos."] + [f"${c:,.0f}" for c in CAPITALS], drows)

    # full history for the 2-asset case
    L += ["## Full history (2018-03 onward) where every asset has data", ""]
    ff = feats
    rows = []
    for name, n in (("BTC", 1), ("BTC+ETH", 2)):
        for k in range(1, n + 1):
            e = stats(run(ff, rules, universe, limits, n, k, EDGE_CAPITAL, EDGE_RISK), None)
            eh = stats(run(ff, hr, universe, limits, n, k, EDGE_CAPITAL, EDGE_RISK), None)
            rows.append([name, k, f"{e['signals_pa']:.1f}", f"{e['trades_pa']:.1f}", f"{e['avg_R']:+.2f}", pct(e["cagr"]),
                         pct(e["max_dd"]), f"{e['sharpe']:.2f}", e["losing_streak"], pct(e["h1"]), pct(e["h2"]), pct(eh["cagr"])])
    L += table(["Universe", "Max pos.", "Signals/yr", "Trades/yr", "Avg R", "CAGR", "Max DD", "Sharpe", "Losing streak",
                "CAGR 1st half", "CAGR 2nd half", "CAGR harsh"], rows)

    # per-asset check, same rules
    L += ["## Each asset alone, same untuned rules (edge test, base fills)", ""]
    rows = []
    for s in ORDER:
        res = run_portfolio({s: feats[s]}, rules, universe, EDGE_CAPITAL, EDGE_RISK, asset_rules=limits)
        e = stats(res)
        bh = feats[s]["close"]
        rows.append([s.split("/")[0], starts[s].date(), e["trades"], f"{e['win_rate']:.0%}", f"{e['avg_R']:+.2f}", pct(e["cagr"]),
                     pct(e["max_dd"]), pct(bh.iloc[-1] / bh.iloc[0] - 1), pct(max_drawdown(bh))])
    L += table(["Asset", "From", "Trades", "Win rate", "Avg R", "CAGR", "Max DD", "Buy & hold", "B&H max DD"], rows)

    # conclusion
    qual = [(n, k, a) for (n, k, a), v in verdicts.items() if v[0] is not None and all(v)]
    L += ["## Which universes pass all four tests?", ""]
    if qual:
        smallest = min(qual, key=lambda t: (COMBOS[t[0]], t[1]))
        L += [f"Passing: {', '.join(f'{n} (max {k}, {a})' for n, k, a in qual)}.",
              f"Smallest passing universe: **{smallest[0]}** with max {smallest[1]} position(s), `{smallest[2]}` allocation."]
    else:
        L += ["**No universe passes all four tests.** BTC-only stays the reference."]
    m2_pass = [k for k, v in verdicts.items() if v[0] is not None and v[1]]
    drop_streak = [k for k, v in verdicts.items() if v[0] is not None and v[0] and v[1] and v[3]]
    L += ["", f"Configurations passing M2 (the dollar-return test): {len(m2_pass)} of {len(verdicts) - 1}. The M3 streak clause "
          "penalises any universe that simply trades more often (more trades means longer streaks in trade counts); it is "
          "kept as pre-registered, but the conclusion does not depend on it, because "
          + ("M2 already fails everywhere." if not m2_pass else f"dropping it would admit {len(drop_streak)} configuration(s) "
             "that still need M2 and M4.")]
    L += ["", f"BTC-only reference on this window: {base_ref['trades_pa']:.1f} trades/yr, CAGR {pct(base_ref['cagr'])}, "
          f"max DD {pct(base_ref['max_dd'])}, avg R {base_ref['avg_R']:+.2f}, harsh CAGR {pct(base_ref_h['cagr'])}.", ""]
    return "\n".join(L)


def main() -> None:
    text = build_report()
    REPORTS_DIR.mkdir(exist_ok=True)
    path = REPORTS_DIR / f"universe_{date.today()}.md"
    path.write_text(text, encoding="utf-8")
    print(text)
    print(f"\nSaved to {path}")


if __name__ == "__main__":
    main()
