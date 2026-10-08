"""Does Laya improve decisions? Walk-forward test against the rules and an information-ceiling model.

Pre-registered verdict: Laya is enabled only if, on 2023+ data it never saw, (1) its ranking of 10-day
outcomes beats chance with the 95% interval above AUC 0.5, and (2) using it as a filter on the rules'
signals improves return/drawdown versus the rules alone.
"""
import argparse
import time
from datetime import date

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from spot_trd.backtest import run_backtest
from spot_trd.config import REPORTS_DIR, ROOT, load_rules, load_universe
from spot_trd.data import load_data
from spot_trd.regime import build_features
from spot_trd.report import fmt_pct, summarize

SPLIT = pd.Timestamp("2023-01-01")
HORIZON = 10
CACHE = ROOT / "data" / "state" / "laya_scores.parquet"
NUMERIC = ["dist20", "dist50", "dist200", "rsi", "atr_pct", "ret10", "ret30", "monthly_up", "spx_weak",
           "dxy20", "gold20", "oil20"]

QUESTIONS = {
    "outlook": {
        "type": "choice",
        "instructions": "Based on this Bitcoin market state, where is the Bitcoin price most likely to be 10 days from now?",
        "criteria": {
            "higher": "noticeably higher than today",
            "unchanged": "roughly the same as today",
            "lower": "noticeably lower than today",
        },
    },
    "buy_now": {
        "type": "noul",
        "instructions": "Is this a favorable moment to buy Bitcoin for a swing trade lasting about two weeks?",
    },
}


def eval_frame(feat: pd.DataFrame, macro: pd.DataFrame) -> pd.DataFrame:
    close = feat["close"]
    f = pd.DataFrame(index=feat.index)
    f["dist20"] = close / feat["ema_pb"] - 1
    f["dist50"] = close / feat["ema_fast"] - 1
    f["dist200"] = close / feat["ema_slow"] - 1
    f["rsi"] = feat["rsi"]
    f["atr_pct"] = feat["atr"] / close
    f["ret10"] = close.pct_change(10)
    f["ret30"] = close.pct_change(30)
    f["monthly_up"] = feat["monthly_up"].astype(float)
    f["spx_weak"] = feat["spx_weak"].astype(float)
    for col, name in (("dxy", "dxy20"), ("gold", "gold20"), ("oil", "oil20")):
        s = macro[col].dropna().clip(lower=1.0)
        f[name] = s.pct_change(20).reindex(f.index, method="ffill")
    f["fwd"] = close.shift(-HORIZON) / close - 1
    f["up"] = (f["fwd"] > 0).astype(float)
    return f.dropna(subset=NUMERIC)


def state_text(r: pd.Series) -> str:
    return (
        f"Bitcoin daily market report. Price is {r.dist20:+.1%} versus its 20-day average, {r.dist50:+.1%} versus "
        f"its 50-day average and {r.dist200:+.1%} versus its 200-day average. RSI(14) is {r.rsi:.0f}. "
        f"Typical daily range is {r.atr_pct:.1%} of price. Bitcoin returned {r.ret10:+.1%} over the past 10 days "
        f"and {r.ret30:+.1%} over the past 30 days. The monthly trend is {'up' if r.monthly_up else 'down'}. "
        f"The S&P 500 is {'below' if r.spx_weak else 'above'} its 50-day average. Over the past 20 trading days "
        f"the US dollar index moved {r.dxy20:+.1%}, gold {r.gold20:+.1%} and oil {r.oil20:+.1%}."
    )


def laya_scores(frame: pd.DataFrame, batch_size: int) -> tuple[pd.DataFrame, dict]:
    import laya

    cached = pd.read_parquet(CACHE) if CACHE.exists() else pd.DataFrame()
    texts = frame.apply(state_text, axis=1)
    todo = texts[[d not in cached.index or cached.loc[d, "state"] != t for d, t in texts.items()]]
    perf = {"cached": len(texts) - len(todo), "scored": len(todo), "device": "-"}
    if len(todo):
        import torch

        perf["device"] = "cuda" if torch.cuda.is_available() else "cpu"
        t0 = time.perf_counter()
        agent = laya.load("convaiinnovations/laya", device=perf["device"])
        perf["load_s"] = time.perf_counter() - t0
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        t0 = time.perf_counter()
        for start in range(0, len(todo), 256):
            chunk = todo.iloc[start:start + 256]
            rows = []
            for d, t, res in zip(chunk.index, chunk, agent.predict_batch(list(chunk), QUESTIONS, batch_size=batch_size)):
                p = res["answers"]["outlook"]["probabilities"]
                rows.append({"date": d, "state": t, "p_higher": p["higher"], "p_unchanged": p["unchanged"],
                             "p_lower": p["lower"], "buy_now": res["answers"]["buy_now"]["noul"]})
            new = pd.DataFrame(rows).set_index("date")
            cached = pd.concat([cached.drop(new.index, errors="ignore"), new]).sort_index()
            cached.to_parquet(CACHE)  # save every chunk so an interrupted run resumes where it stopped
            print(f"  Laya scored {min(start + 256, len(todo))}/{len(todo)} days on {perf['device']}", flush=True)
        perf["infer_s"] = time.perf_counter() - t0
    out = cached.loc[frame.index]
    out["laya_score"] = out["p_higher"] - out["p_lower"]
    return out, perf


def block_bootstrap_auc(y: np.ndarray, s: np.ndarray, block: int = 20, draws: int = 2000, seed: int = 7) -> tuple:
    """AUC with a moving-block bootstrap CI; overlapping 10-day outcomes make plain resampling overconfident."""
    rng = np.random.default_rng(seed)
    n = len(y)
    starts = np.arange(n - block + 1)
    aucs = []
    for _ in range(draws):
        idx = np.concatenate([np.arange(b, b + block) for b in rng.choice(starts, size=n // block + 1)])[:n]
        if len(np.unique(y[idx])) == 2:
            aucs.append(roc_auc_score(y[idx], s[idx]))
    return roc_auc_score(y, s), np.percentile(aucs, 2.5), np.percentile(aucs, 97.5)


def filtered_backtest(feat: pd.DataFrame, score: pd.Series, threshold: float, rules: dict, universe: dict,
                      lo: pd.Timestamp | None, hi: pd.Timestamp | None) -> dict:
    f = feat.copy()
    if score is not None:
        f["signal"] = f["signal"] & (score.reindex(f.index) >= threshold).fillna(False)
    if lo is not None:
        f = f[f.index >= lo]
    if hi is not None:
        f = f[f.index < hi]
    res = run_backtest(f, rules, universe, 100_000.0, 0.02)
    return summarize(res.trades, res.equity, res.initial)


def main() -> None:
    ap = argparse.ArgumentParser(description="Evaluate Laya against the rules, walk-forward.")
    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--limit", type=int, help="only score the most recent N days (quick smoke test)")
    args = ap.parse_args()

    rules, universe = load_rules(), load_universe()
    btc, macro = load_data()
    feat = build_features(btc, macro, rules)
    frame = eval_frame(feat, macro)
    if args.limit:
        frame = frame.iloc[-args.limit:]

    t0 = time.perf_counter()
    build_features(btc, macro, rules)
    rules_ms = (time.perf_counter() - t0) * 1000 / len(feat)
    scores, perf = laya_scores(frame, args.batch_size)
    frame = frame.join(scores[["p_higher", "p_lower", "buy_now", "laya_score"]])

    labeled = frame.dropna(subset=["fwd"])
    purge = SPLIT - pd.Timedelta(days=HORIZON)  # drop training rows whose outcome overlaps the test period
    train, test = labeled[labeled.index < purge], labeled[labeled.index >= SPLIT]

    enough = len(train) > 200 and len(test) > 60
    if enough:
        model = make_pipeline(StandardScaler(), LogisticRegression(C=0.1, max_iter=1000))
        model.fit(train[NUMERIC], train["up"])
        test = test.assign(ceiling=model.predict_proba(test[NUMERIC])[:, 1])
        platt = LogisticRegression().fit(train[["laya_score"]], train["up"])
        test = test.assign(laya_calibrated=platt.predict_proba(test[["laya_score"]])[:, 1])

    lines = [
        f"# Laya evaluation ({date.today()})", "",
        "Question: does Laya (convaiinnovations/laya, zero-shot) improve decisions beyond the rules?",
        f"Target: is BTC higher {HORIZON} days later? Selected and calibrated on 2018-2022; judged on "
        f"{test.index[0].date() if len(test) else '-'} to {test.index[-1].date() if len(test) else '-'} ({len(test)} days).",
        "",
        "## Ranking skill on unseen 2023+ days (AUC 0.5 = coin flip)", "",
        "| Signal | AUC | 95% interval | Beats chance? |", "|---|---|---|---|",
    ]
    verdicts = {}
    if enough:
        for name, col in (("Laya outlook (P higher - P lower)", "laya_score"), ("Laya 'buy now?' yes/no", "buy_now"),
                          ("Rules: regime gate passes", None), ("Information ceiling: logistic regression on the same numbers", "ceiling")):
            s = test[col].to_numpy() if col else feat.loc[test.index, "regime_ok"].astype(float).to_numpy()
            auc, lo, hi = block_bootstrap_auc(test["up"].to_numpy(), s)
            verdicts[name] = lo > 0.5
            lines.append(f"| {name} | {auc:.3f} | {lo:.3f} to {hi:.3f} | {'yes' if lo > 0.5 else 'no'} |")
        ic = test["laya_score"].corr(test["fwd"], method="spearman")
        brier_raw = ((test["p_higher"] - test["up"]) ** 2).mean()
        brier_cal = ((test["laya_calibrated"] - test["up"]) ** 2).mean()
        brier_base = ((train["up"].mean() - test["up"]) ** 2).mean()
        lines += [
            "",
            f"Rank correlation of the Laya score with the actual 10-day return: {ic:+.3f}.",
            f"Probability accuracy (Brier, lower is better): Laya raw {brier_raw:.4f}, Laya calibrated on 2018-2022 "
            f"{brier_cal:.4f}, always guessing the historical up-rate {brier_base:.4f}.",
        ]
    else:
        lines.append("Too few unseen days scored for a verdict (use the full run, not --limit).")

    trade_better = False
    sig_is = frame.index[(frame.index < SPLIT)].intersection(feat.index[feat["signal"]])
    if len(sig_is) and enough:
        thr = frame.loc[sig_is, "laya_score"].median()
        base_is = filtered_backtest(feat, None, 0, rules, universe, None, SPLIT)
        base_oos = filtered_backtest(feat, None, 0, rules, universe, SPLIT, None)
        lf_is = filtered_backtest(feat, frame["laya_score"], thr, rules, universe, None, SPLIT)
        lf_oos = filtered_backtest(feat, frame["laya_score"], thr, rules, universe, SPLIT, None)
        mar = lambda s: s["total_return"] / max(abs(s["max_drawdown"]), 0.01)
        trade_better = mar(lf_oos) > mar(base_oos)
        row = lambda n, s: (f"| {n} | {s['trades']} | {s['avg_R']:+.2f} | {fmt_pct(s['total_return'])} | "
                            f"{fmt_pct(s['max_drawdown'])} |")
        lines += [
            "", f"## Trading impact: take only signals where the Laya score is above its 2018-2022 median ({thr:+.3f})", "",
            "| Variant | Trades | Avg R | Return | Max DD |", "|---|---|---|---|---|",
            row("Rules v2, 2018-2022", base_is), row("Rules v2 + Laya filter, 2018-2022", lf_is),
            row("Rules v2, 2023-now", base_oos), row("Rules v2 + Laya filter, 2023-now", lf_oos),
        ]

    per_state = perf.get("infer_s", float("nan")) / max(perf["scored"], 1) * 1000
    lines += [
        "", f"## Efficiency on this PC ({perf['device']})", "",
        f"- Laya: model load {perf.get('load_s', float('nan')):.1f}s, ~{per_state:.0f} ms per daily decision "
        f"({perf['scored']} newly scored, {perf['cached']} from cache), about 1.7 GB of weights on disk.",
        f"- Rules: ~{rules_ms:.3f} ms per day of history for all indicators and gates.",
        "- For one decision a day, both are instant in practice. Speed isn't the question; decision quality is.",
    ]
    laya_ok = verdicts.get("Laya outlook (P higher - P lower)", False) and trade_better
    ceiling_ok = verdicts.get("Information ceiling: logistic regression on the same numbers", False)
    lines += ["", "## Verdict", ""]
    if not enough:
        lines.append("NO VERDICT: not enough scored history. Run without --limit.")
    elif laya_ok:
        lines.append("ENABLE as a filter: Laya beat chance on unseen data and improved the rules' return/drawdown.")
    else:
        lines.append("SKIP Laya: it did not beat chance on unseen data and/or did not improve trading results.")
        lines.append(
            "- Fine-tuning outlook: " + (
                "the ceiling model *does* find signal in these numbers, so a fine-tuned Laya might help; worth a "
                "Kaggle GPU fine-tune experiment." if ceiling_ok else
                "even a model trained directly on these numbers can't rank unseen 10-day outcomes better than "
                "chance, so fine-tuning Laya on the same information is very unlikely to create an edge."))
    text = "\n".join(lines)
    REPORTS_DIR.mkdir(exist_ok=True)
    path = REPORTS_DIR / f"laya_eval_{date.today()}.md"
    path.write_text(text, encoding="utf-8")
    print(text)
    print(f"\nSaved to {path}")


if __name__ == "__main__":
    main()
