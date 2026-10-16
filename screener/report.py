"""Écriture des fichiers lus par le site (JSON), exports CSV / Excel, historique."""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from . import __version__
from . import backtest as B
from . import ic as IC
from .config import FACTOR_LABELS, FACTORS, HISTORY_DIR, SITE_DATA_DIR
from .features import METRIC_LABELS, METRICS

RUN_LABELS = {
    "reference": "Référence",
    "equal_weights": "Poids égaux (5 × 20 %)",
    "trend_filter": "Filtre moyenne mobile 200 jours",
    "fixed_12m": "Détention fixe de 12 mois",
    "review_shift_1m": "Revues décalées d'un mois",
    "positions_15": "15 lignes",
    "positions_30": "30 lignes",
    "weights_a": "Poids A (croissance 30 %, valorisation 10 %)",
    "weights_b": "Poids B (croissance 20 %, qualité 25 %)",
}
BENCH_LABELS = {"sp500": "S&P 500 (dividendes réinvestis)", "equal_weight": "S&P 500 équipondéré"}
EXTRA = ["revenue_ttm", "oi_ttm", "net_debt", "net_debt_ebitda", "market_cap",
         "enterprise_value", "known_date", "quarter_end", "fundamentals_age_days",
         "dollar_vol_63", "above_sma200", "ret_1y", "revenue_tag", "price_adj"]


def clean(obj):
    """Rend un objet sérialisable en JSON (NaN -> null, dates -> texte)."""
    if isinstance(obj, dict):
        return {str(k): clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    if isinstance(obj, (pd.Timestamp, datetime)):
        return None if pd.isna(obj) else obj.strftime("%Y-%m-%d")
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        return None if (math.isnan(obj) or math.isinf(obj)) else round(float(obj), 6)
    if obj is pd.NaT or (obj is not None and not isinstance(obj, str) and pd.api.types.is_scalar(obj)
                         and pd.isna(obj)):
        return None
    return obj


def dump(name: str, obj) -> None:
    SITE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(SITE_DATA_DIR / name, "w", encoding="utf-8") as f:
        json.dump(clean(obj), f, ensure_ascii=False, separators=(",", ":"))


def _val(x):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else x


def ranking_rows(live: pd.DataFrame, holdings: set, actions: dict) -> list[dict]:
    rows = []
    order = live.sort_values(["eligible", "rank", "composite"], ascending=[False, True, False])
    for t, r in order.iterrows():
        rows.append({
            "ticker": t, "name": r.get("name"), "sector": r.get("sector"),
            "sub_industry": r.get("sub_industry"), "cik": r.get("cik"),
            "price": r.get("price"), "rank": r.get("rank"), "eligible": bool(r["eligible"]),
            "reasons": r.get("reason_text") or [], "score": r.get("composite"),
            "factors": {f: r.get(f) for f in FACTORS},
            "pct": {m: r.get(f"pct_{m}") for m in METRICS},
            "metrics": {m: r.get(m) for m in METRICS},
            "extra": {k: r.get(k) for k in EXTRA},
            "confidence": r.get("data_confidence"), "flags": r.get("flags") or "",
            "last_earnings": r.get("last_earnings"), "next_earnings_est": r.get("next_earnings_est"),
            "in_portfolio": t in holdings, "action": actions.get(t, ""),
        })
    return rows


def fr(x: float, digits: int = 2, plus: bool = True) -> str:
    """Nombre au format français, avec signe moins typographique."""
    s = f"{x:+.{digits}f}" if plus else f"{x:.{digits}f}"
    return s.replace("-", "−").replace(".", ",")


def evaluate_criteria(metrics_by_run: dict, ic_summary: list[dict]) -> list[dict]:
    out = []
    ref = metrics_by_run.get("reference", {})
    subs = ref.get("subperiods") or []
    ex = [s.get("excess_equal_weight") for s in subs]
    if len(ex) == 2 and all(v is not None for v in ex):
        out.append({"id": "excess_vs_equal_weight_each_subperiod",
                    "status": "réussi" if all(v > 0 for v in ex) else "échoué",
                    "detail": " ; ".join(f"{fr(v * 100)} %/an" for v in ex)})
    else:
        out.append({"id": "excess_vs_equal_weight_each_subperiod", "status": "non évaluable",
                    "detail": "sous-périodes incomplètes"})
    ic12 = {r["factor"]: r["mean_ic"] for r in ic_summary if r["horizon"] == 12}
    if all(f in ic12 for f in FACTORS):
        bad = [FACTOR_LABELS[f] for f in FACTORS if ic12[f] <= 0]
        out.append({"id": "factor_ic_12m_positive", "status": "réussi" if not bad else "échoué",
                    "detail": ", ".join(f"{FACTOR_LABELS[f]} {fr(ic12[f], 3)}" for f in FACTORS)})
    else:
        out.append({"id": "factor_ic_12m_positive", "status": "non évaluable",
                    "detail": "historique insuffisant"})
    ref_ex = (ref.get("design") or {}).get("excess_equal_weight")
    robust = [n for n in ("review_shift_1m", "positions_15", "positions_30", "weights_a",
                          "weights_b") if n in metrics_by_run]
    if ref_ex is not None and robust:
        same = [n for n in robust if (metrics_by_run[n].get("design") or {}).get(
            "excess_equal_weight") is not None and np.sign(
            metrics_by_run[n]["design"]["excess_equal_weight"]) == np.sign(ref_ex)]
        out.append({"id": "robustness_same_sign",
                    "status": "réussi" if len(same) >= 4 else "échoué",
                    "detail": f"{len(same)} test(s) sur {len(robust)} de même signe"})
    else:
        out.append({"id": "robustness_same_sign", "status": "non évaluable", "detail": ""})
    return out


def yearly_returns(series: dict[str, pd.Series], end) -> list[dict]:
    rows = {}
    for name, s in series.items():
        s = s.loc[:end].dropna()
        y = s.resample("YE").last()
        first = s.iloc[0]
        prev = first
        for d, v in y.items():
            rows.setdefault(d.year, {})[name] = float(v / prev - 1)
            prev = v
    return [{"year": y, **v} for y, v in sorted(rows.items())]


def write_all(*, settings, protocol, live, runs, groups, bench, rf_daily, ic_obs, audit, status,
              hypo, next_review_date, today, valid_start, prices, panel_dates) -> None:
    revealed = bool(protocol["holdout"]["revealed"])
    design_end = pd.Timestamp(protocol["design_period"]["end"])
    visible_end = today if revealed else design_end
    start = str(valid_start.date())

    # --- Backtest -----------------------------------------------------------
    metrics_by_run = {}
    for name, res in runs.items():
        m = {"design": B.metrics(res, bench, rf_daily, start, str(design_end.date())),
             "subperiods": [B.metrics(res, bench, rf_daily, max(a, start), b)
                            for a, b in protocol["subperiods"]]}
        if revealed:
            m["holdout"] = B.metrics(res, bench, rf_daily, protocol["holdout"]["start"], None)
            m["full"] = B.metrics(res, bench, rf_daily, start, None)
        metrics_by_run[name] = m

    curves = {}
    for name in groups["variants"]:
        s = runs[name].equity.loc[:visible_end]
        curves[name] = B.weekly(s / s.iloc[0])
    for key, b in bench.items():
        s = b.loc[valid_start:visible_end].dropna()
        if len(s):
            curves[key] = B.weekly(s / s.iloc[0])
    ref_eq = runs["reference"].equity.loc[:visible_end]
    dd = B.weekly(ref_eq / ref_eq.cummax() - 1)
    idx = sorted(set().union(*[set(c.index) for c in curves.values()]))
    curve_rows = [{"date": d, **{k: (c.get(d) if d in c.index else None)
                                 for k, c in curves.items()}} for d in idx]

    ic_summary = IC.summarize(ic_obs) if len(ic_obs) else []
    criteria = evaluate_criteria(metrics_by_run, ic_summary)
    crit_text = protocol.get("criteria", {})
    for c in criteria:
        c["text"] = " ".join(str(crit_text.get(c["id"], "")).split())

    yearly = yearly_returns({"reference": runs["reference"].equity,
                             **{k: v.loc[valid_start:] for k, v in bench.items()}}, visible_end)
    sectors_hist = []
    sector_of = live["sector"].to_dict()
    for rv in runs["reference"].reviews:
        if rv["executed"] > visible_end:
            continue
        counts = {}
        for t in rv["holdings"]:
            counts[sector_of.get(t) or "Autre / ancien membre"] = \
                counts.get(sector_of.get(t) or "Autre / ancien membre", 0) + 1
        sectors_hist.append({"date": rv["executed"], **counts})

    dump("backtest.json", {
        "revealed": revealed, "start": start, "design_end": design_end,
        "holdout_start": protocol["holdout"]["start"], "subperiods": protocol["subperiods"],
        "labels": {**RUN_LABELS, **BENCH_LABELS},
        "variants": list(groups["variants"]), "robustness": list(groups["robustness"]),
        "metrics": metrics_by_run, "curves": curve_rows,
        "drawdown": [{"date": d, "value": v} for d, v in dd.items()],
        "yearly": yearly, "criteria": criteria, "sector_history": sectors_hist,
        "cost_per_trade": settings["portfolio"]["cost_per_trade"],
    })

    # --- Analyse par facteur --------------------------------------------------
    dump("factors.json", {
        "revealed": revealed, "end_limit": visible_end,
        "horizons": protocol["ic_horizons_months"],
        "labels": {**FACTOR_LABELS, "composite": "Score global"},
        "summary": ic_summary,
        "decay": IC.decay(ic_obs) if len(ic_obs) else [],
        "by_year": IC.by_year(ic_obs, 12) if len(ic_obs) else [],
    })

    # --- Portefeuille -------------------------------------------------------------
    ref = runs["reference"]
    holdings = set(ref.holdings)
    actions = {t: "garder" for t in hypo.keep} | {t: "vendre" for t in hypo.sell} | \
              {t: "acheter" for t in hypo.buy}
    last_review = ref.reviews[-1] if ref.reviews else None
    hold_rows = []
    for t, h in ref.holdings.items():
        r = live.loc[t] if t in live.index else None
        hold_rows.append({
            "ticker": t, "name": None if r is None else r.get("name"),
            "sector": None if r is None else r.get("sector"),
            "entry_date": h["entry_date"], "return": h["last_price"] / h["entry_price"] - 1
            if h["entry_price"] else None,
            "weight": h["weight"], "rank": None if r is None else r.get("rank"),
            "score": None if r is None else r.get("composite"),
            "action": actions.get(t, "vendre"),
            "sell_reason": hypo.sell_reasons.get(t, ""),
        })
    hold_rows.sort(key=lambda x: (x["rank"] is None, x["rank"] or 0))
    buys = [{"ticker": t, "name": live.at[t, "name"], "sector": live.at[t, "sector"],
             "rank": live.at[t, "rank"], "score": live.at[t, "composite"]} for t in hypo.buy]
    recent = [{"review_date": rv["review_date"], "executed": rv["executed"], "buy": rv["buy"],
               "sell": rv["sell"]} for rv in ref.reviews[-6:]]
    dump("portfolio.json", {
        "as_of": today, "next_review": next_review_date,
        "last_review": None if last_review is None else {
            "review_date": last_review["review_date"], "executed": last_review["executed"]},
        "params": {k: v for k, v in settings["portfolio"].items()},
        "holdings": hold_rows, "hypothetical_buys": buys,
        "recent_reviews": recent,
    })

    # --- Classement -----------------------------------------------------------
    rows = ranking_rows(live, holdings, actions)
    dump("ranking.json", {"as_of": today, "rows": rows})
    export_tables(live, hold_rows, today)
    changes = snapshot_and_changes(live, today)
    dump("changes.json", changes)

    # --- Audit et méta ------------------------------------------------------------
    dump("audit.json", audit)
    dump("meta.json", {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "version": __version__, "model_version": settings["model_version"],
        "as_of": today, "price_last_date": prices["close"].index[-1],
        "sec_refreshed_at": status.get("sec_refreshed_at"),
        "history_last_date": status.get("history_last_date"),
        "constituents_source": status.get("constituents_source"),
        "warnings": status.get("warnings", []),
        "weights": settings["weights"], "scoring": settings["scoring"],
        "universe": settings["universe"], "portfolio": settings["portfolio"],
        "factor_labels": FACTOR_LABELS, "metric_labels": METRIC_LABELS,
        "metric_factor": {m: spec[0] for m, spec in METRICS.items()},
        "metric_direction": {m: spec[1] for m, spec in METRICS.items()},
        "metric_by_sector": {m: spec[2] for m, spec in METRICS.items()},
        "protocol": {"frozen_on": protocol["frozen_on"], "design_period": protocol["design_period"],
                     "holdout": protocol["holdout"], "subperiods": protocol["subperiods"]},
        "counts": {"members": len(live), "eligible": int(live["eligible"].sum()),
                   "panel_dates": panel_dates},
    })


def export_tables(live: pd.DataFrame, hold_rows: list[dict], today) -> None:
    cols = {"rank": "Rang", "name": "Société", "sector": "Secteur", "composite": "Score",
            **{f: FACTOR_LABELS[f] for f in FACTORS},
            **{m: METRIC_LABELS[m] for m in METRICS},
            "data_confidence": "Confiance données (%)", "price": "Cours ($)",
            "market_cap": "Capitalisation ($)", "known_date": "Dernier dépôt SEC",
            "next_earnings_est": "Prochains résultats (estimés)"}
    t = live.sort_values(["eligible", "rank"], ascending=[False, True])
    out = t[[c for c in cols if c in t.columns]].rename(columns=cols)
    out.insert(0, "Ticker", t.index)
    out["Éligible"] = np.where(t["eligible"], "oui", "non")
    out["Motifs d'exclusion"] = t["reason_text"].map(lambda r: " ; ".join(r or []))
    out.to_csv(SITE_DATA_DIR / "classement.csv", index=False, encoding="utf-8-sig")
    port = pd.DataFrame(hold_rows).rename(columns={
        "ticker": "Ticker", "name": "Société", "sector": "Secteur", "entry_date": "Entrée",
        "return": "Rendement depuis l'entrée", "weight": "Poids", "rank": "Rang actuel",
        "score": "Score", "action": "À la prochaine revue", "sell_reason": "Motif de vente"})
    method = pd.DataFrame({"Méthode": [
        f"Classement au {pd.Timestamp(today).date()} - aide à la décision, pas un conseil.",
        "Score = moyenne pondérée de 5 facteurs (percentiles 0-100).",
        "Fondamentaux : SEC EDGAR (XBRL), première valeur publiée, utilisable le lendemain du dépôt.",
        "Cours : Yahoo Finance via yfinance (source non officielle).",
        "Banques, assureurs et immobilier exclus en V1.",
    ]})
    with pd.ExcelWriter(SITE_DATA_DIR / "classement.xlsx", engine="openpyxl") as xw:
        out.to_excel(xw, sheet_name="Classement", index=False)
        port.to_excel(xw, sheet_name="Portefeuille", index=False)
        method.to_excel(xw, sheet_name="Méthode", index=False)


def snapshot_and_changes(live: pd.DataFrame, today) -> dict:
    d = HISTORY_DIR / "rankings"
    d.mkdir(parents=True, exist_ok=True)
    today = pd.Timestamp(today)
    snap = live[["rank", "composite", "eligible", *FACTORS]].copy()
    snap.index.name = "ticker"
    snap.round(2).to_csv(d / f"{today.date()}.csv")
    files = sorted(d.glob("*.csv"))
    for f in files:   # on garde les vendredis et les 10 derniers jours
        fd = pd.Timestamp(f.stem)
        if (today - fd).days > 10 and fd.weekday() != 4:
            f.unlink()
    files = sorted(d.glob("*.csv"))
    older = [f for f in files if pd.Timestamp(f.stem) <= today - pd.Timedelta(days=7)]
    ref_file = older[-1] if older else (files[0] if files and files[0].stem != str(today.date())
                                        else None)
    if ref_file is None:
        return {"available": False, "as_of": today}
    prev = pd.read_csv(ref_file, index_col="ticker")
    cur_top = set(snap.index[snap["rank"] <= 20])
    prev_top = set(prev.index[prev["rank"] <= 20])
    both = snap.index.intersection(prev.index)
    moves = []
    for t in both:
        a, b = prev.at[t, "rank"], snap.at[t, "rank"]
        if pd.notna(a) and pd.notna(b) and abs(a - b) >= 10 and min(a, b) <= 60:
            moves.append({"ticker": t, "name": live.at[t, "name"], "from": a, "to": b})
    moves.sort(key=lambda x: abs(x["from"] - x["to"]), reverse=True)
    newly_inel = [t for t in both if prev.at[t, "eligible"] and not snap.at[t, "eligible"]]
    newly_el = [t for t in both if not prev.at[t, "eligible"] and snap.at[t, "eligible"]]
    return {
        "available": True, "as_of": today, "compared_to": ref_file.stem,
        "entered_top20": sorted(cur_top - prev_top), "left_top20": sorted(prev_top - cur_top),
        "big_moves": moves[:25], "became_eligible": sorted(newly_el),
        "became_ineligible": sorted(newly_inel),
    }
