"""Écriture des fichiers lus par le site (JSON), exports CSV / Excel, historique."""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from . import __version__
from . import backtest as B
from . import config as C
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
EXTRA = ["sue_quarter", "revenue_ttm", "oi_ttm", "net_debt", "net_debt_ebitda", "market_cap",
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


def ranking_rows(live: pd.DataFrame, models: list[str], ports: dict, dm: str) -> list[dict]:
    rows = []
    order = live.sort_values([f"eligible_{dm}", f"rank_{dm}"], ascending=[False, True])
    for t, r in order.iterrows():
        per = {}
        for m in models:
            per[m] = {"score": r.get(f"composite_{m}"), "rank": r.get(f"rank_{m}"),
                      "eligible": bool(r[f"eligible_{m}"]),
                      "reasons": r.get(f"reason_text_{m}") or [],
                      "in_portfolio": t in ports[m]["holdings"],
                      "action": ports[m]["actions"].get(t, "")}
        rows.append({
            "ticker": t, "name": r.get("name"), "sector": r.get("sector"),
            "sub_industry": r.get("sub_industry"), "cik": r.get("cik"), "price": r.get("price"),
            "factors": {f: r.get(f) for f in FACTORS},
            "pct": {m: r.get(f"pct_{m}") for m in METRICS},
            "metrics": {m: r.get(m) for m in METRICS},
            "extra": {k: r.get(k) for k in EXTRA},
            "confidence": r.get("data_confidence"), "flags": r.get("flags") or "",
            "last_earnings": r.get("last_earnings"), "next_earnings_est": r.get("next_earnings_est"),
            "models": per,
        })
    return rows


def fr(x: float, digits: int = 2, plus: bool = True) -> str:
    """Nombre au format français, avec signe moins typographique."""
    s = f"{x:+.{digits}f}" if plus else f"{x:.{digits}f}"
    return s.replace("-", "−").replace(".", ",")


def evaluate_criteria(metrics: dict, ic_summary: list[dict], success: list[dict],
                      weights: dict, model: str) -> list[dict]:
    """Critères du protocole pour un modèle. `metrics` : variante -> mesures."""
    out = []
    ref = metrics.get("reference", {})
    ex = [s.get("excess_equal_weight") for s in ref.get("subperiods") or []]
    if len(ex) == 2 and all(v is not None for v in ex):
        out.append({"id": "excess_vs_equal_weight_each_subperiod",
                    "status": "réussi" if all(v > 0 for v in ex) else "échoué",
                    "detail": " ; ".join(f"{fr(v * 100)} %/an" for v in ex)})
    else:
        out.append({"id": "excess_vs_equal_weight_each_subperiod", "status": "non évaluable",
                    "detail": "sous-périodes incomplètes"})
    active = [f for f in FACTORS if weights.get(f, 0) > 0]
    ic12 = {r["factor"]: r["mean_ic"] for r in ic_summary if r["horizon"] == 12}
    if all(f in ic12 for f in active):
        bad = [f for f in active if ic12[f] <= 0]
        out.append({"id": "factor_ic_12m_positive", "status": "réussi" if not bad else "échoué",
                    "detail": ", ".join(f"{FACTOR_LABELS[f]} {fr(ic12[f], 3)}" for f in active)})
    else:
        out.append({"id": "factor_ic_12m_positive", "status": "non évaluable",
                    "detail": "historique insuffisant"})
    ref_ex = (ref.get("design") or {}).get("excess_equal_weight")
    robust = [n for n in ("review_shift_1m", "positions_15", "positions_30", "weights_a",
                          "weights_b") if n in metrics]
    if ref_ex is not None and robust:
        same = [n for n in robust if (metrics[n].get("design") or {}).get(
            "excess_equal_weight") is not None and np.sign(
            metrics[n]["design"]["excess_equal_weight"]) == np.sign(ref_ex)]
        out.append({"id": "robustness_same_sign",
                    "status": "réussi" if len(same) >= 4 else "échoué",
                    "detail": f"{len(same)} test(s) sur {len(robust)} de même signe"})
    else:
        out.append({"id": "robustness_same_sign", "status": "non évaluable", "detail": ""})
    s12 = next((x for x in success if x["horizon"] == 12), None)
    if s12:
        out.append({"id": "top20_beats_base_rate_12m",
                    "status": "réussi" if s12["top_rate"] > s12["base_rate"] else "échoué",
                    "detail": f"top 20 : {fr(s12['top_rate'] * 100, 1, False)} % ; "
                              f"taux de base : {fr(s12['base_rate'] * 100, 1, False)} %"})
    else:
        out.append({"id": "top20_beats_base_rate_12m", "status": "non évaluable", "detail": ""})
    return out


def yearly_returns(series: dict[str, pd.Series], end) -> list[dict]:
    rows = {}
    for name, s in series.items():
        s = s.loc[:end].dropna()
        if s.empty:
            continue
        y = s.resample("YE").last()
        prev = s.iloc[0]
        for d, v in y.items():
            rows.setdefault(d.year, {})[name] = float(v / prev - 1)
            prev = v
    return [{"year": y, **v} for y, v in sorted(rows.items())]


def portfolio_block(live: pd.DataFrame, port: dict, model: str) -> dict:
    ref, hypo = port["result"], port["hypo"]
    actions = {t: "garder" for t in hypo.keep} | {t: "vendre" for t in hypo.sell} | \
              {t: "acheter" for t in hypo.buy}
    hold_rows = []
    for t, h in ref.holdings.items():
        r = live.loc[t] if t in live.index else None
        hold_rows.append({
            "ticker": t, "name": None if r is None else r.get("name"),
            "sector": None if r is None else r.get("sector"),
            "entry_date": h["entry_date"], "return": h["last_price"] / h["entry_price"] - 1
            if h["entry_price"] else None,
            "weight": h["weight"], "rank": None if r is None else r.get(f"rank_{model}"),
            "score": None if r is None else r.get(f"composite_{model}"),
            "action": actions.get(t, "vendre"),
            "sell_reason": hypo.sell_reasons.get(t, ""),
        })
    hold_rows.sort(key=lambda x: (x["rank"] is None or pd.isna(x["rank"]), x["rank"] or 0))
    buys = [{"ticker": t, "name": live.at[t, "name"], "sector": live.at[t, "sector"],
             "rank": live.at[t, f"rank_{model}"], "score": live.at[t, f"composite_{model}"]}
            for t in hypo.buy]
    last = ref.reviews[-1] if ref.reviews else None
    return {
        "holdings": hold_rows, "hypothetical_buys": buys,
        "recent_reviews": [{"review_date": rv["review_date"], "executed": rv["executed"],
                            "buy": rv["buy"], "sell": rv["sell"]} for rv in ref.reviews[-6:]],
        "last_review": None if last is None else {"review_date": last["review_date"],
                                                  "executed": last["executed"]},
        "_holdings": set(ref.holdings), "_actions": actions,
    }


def write_all(*, settings, protocol, live, runs, groups, bench, rf_daily, ic_obs, success, audit,
              status, portfolios, next_review_date, today, valid_start, prices,
              panel_dates) -> None:
    revealed = bool(protocol["holdout"]["revealed"])
    design_end = pd.Timestamp(protocol["design_period"]["end"])
    visible_end = today if revealed else design_end
    start = str(valid_start.date())
    models = list(protocol["models"])
    ic_summary = IC.summarize(ic_obs) if len(ic_obs) else []

    # --- Backtest -----------------------------------------------------------
    per_model = {}
    curves = {}
    for model in models:
        metrics = {}
        for name in list(groups["variants"]) + list(groups["robustness"]):
            res = runs[f"{model}:{name}"]
            m = {"design": B.metrics(res, bench, rf_daily, start, str(design_end.date())),
                 "subperiods": [B.metrics(res, bench, rf_daily, max(a, start), b)
                                for a, b in protocol["subperiods"]]}
            if revealed:
                m["holdout"] = B.metrics(res, bench, rf_daily, protocol["holdout"]["start"], None)
                m["full"] = B.metrics(res, bench, rf_daily, start, None)
            metrics[name] = m
        for name in groups["variants"]:
            s = runs[f"{model}:{name}"].equity.loc[:visible_end]
            curves[model if name == "reference" else f"{model}:{name}"] = B.weekly(s / s.iloc[0])
        ref_eq = runs[f"{model}:reference"].equity.loc[:visible_end]
        dd = B.weekly(ref_eq / ref_eq.cummax() - 1)
        model_ic = [r for r in ic_summary if r["factor"] in FACTORS]
        criteria = evaluate_criteria(metrics, model_ic, success.get(model, []),
                                     settings["models"][model]["weights"], model)
        crit_text = protocol.get("criteria", {})
        for c in criteria:
            c["text"] = " ".join(str(crit_text.get(c["id"], "")).split())
        per_model[model] = {
            "metrics": metrics, "criteria": criteria,
            "drawdown": [{"date": d, "value": v} for d, v in dd.items()],
            "success": success.get(model, []),
        }
    for key, b in bench.items():
        s = b.loc[valid_start:visible_end].dropna()
        if len(s):
            curves[key] = B.weekly(s / s.iloc[0])
    idx = sorted(set().union(*[set(c.index) for c in curves.values()]))
    curve_rows = [{"date": d, **{k: (c.get(d) if d in c.index else None)
                                 for k, c in curves.items()}} for d in idx]
    yearly = yearly_returns({**{m: runs[f"{m}:reference"].equity for m in models},
                             **{k: v.loc[valid_start:] for k, v in bench.items()}}, visible_end)
    model_labels = {m: settings["models"][m]["label"] for m in models}
    dump("backtest.json", {
        "revealed": revealed, "start": start, "design_end": design_end,
        "holdout_start": protocol["holdout"]["start"], "subperiods": protocol["subperiods"],
        "labels": {**RUN_LABELS, **BENCH_LABELS, **model_labels},
        "models": models, "variants": list(groups["variants"]),
        "robustness": list(groups["robustness"]), "per_model": per_model,
        "curves": curve_rows, "yearly": yearly,
        "cost_per_trade": settings["portfolio"]["cost_per_trade"],
        "success_top_n": protocol.get("success_top_n", 20),
    })

    # --- Analyse par facteur --------------------------------------------------
    dump("factors.json", {
        "revealed": revealed, "end_limit": visible_end,
        "horizons": protocol["ic_horizons_months"],
        "labels": {**FACTOR_LABELS, **{f"composite_{m}": f"Score {model_labels[m]}"
                                       for m in models}},
        "order": FACTORS + [f"composite_{m}" for m in models],
        "summary": ic_summary,
        "decay": IC.decay(ic_obs) if len(ic_obs) else [],
        "by_year": IC.by_year(ic_obs, 12) if len(ic_obs) else [],
    })

    # --- Portefeuilles ------------------------------------------------------------
    blocks = {m: portfolio_block(live, portfolios[m], m) for m in models}
    ports = {m: {"holdings": b.pop("_holdings"), "actions": b.pop("_actions")}
             for m, b in blocks.items()}
    dump("portfolio.json", {
        "as_of": today, "next_review": next_review_date,
        "params": {k: v for k, v in settings["portfolio"].items()},
        "models": blocks,
    })

    # --- Classement -----------------------------------------------------------
    dm = settings["default_model"]
    rows = ranking_rows(live, models, ports, dm)
    dump("ranking.json", {"as_of": today, "rows": rows})
    export_tables(live, blocks, models, model_labels, today, dm)
    dump("changes.json", snapshot_and_changes(live, models, today))

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
        "models": {m: {"label": model_labels[m],
                       "weights": {f: float(settings["models"][m]["weights"].get(f, 0.0))
                                   for f in FACTORS}} for m in models},
        "default_model": settings["default_model"],
        "factors": FACTORS, "scoring": settings["scoring"],
        "universe": settings["universe"], "portfolio": settings["portfolio"],
        "factor_labels": FACTOR_LABELS, "metric_labels": METRIC_LABELS,
        "metric_factor": {m: spec[0] for m, spec in METRICS.items()},
        "metric_direction": {m: spec[1] for m, spec in METRICS.items()},
        "metric_by_sector": {m: spec[2] for m, spec in METRICS.items()},
        "protocol": {"frozen_on": protocol["frozen_on"], "design_period": protocol["design_period"],
                     "holdout": protocol["holdout"], "subperiods": protocol["subperiods"]},
        "counts": {"members": len(live),
                   "eligible": {m: int(live[f"eligible_{m}"].sum()) for m in models},
                   "panel_dates": panel_dates},
    })


def export_tables(live: pd.DataFrame, blocks: dict, models: list[str], labels: dict,
                  today, dm: str) -> None:
    cols = {"name": "Société", "sector": "Secteur",
            **{c: n for m in models for c, n in ((f"rank_{m}", f"Rang {labels[m]}"),
                                                 (f"composite_{m}", f"Score {labels[m]}"))},
            **{f: FACTOR_LABELS[f] for f in FACTORS},
            **{m: METRIC_LABELS[m] for m in METRICS},
            "data_confidence": "Mesures disponibles (%)", "price": "Cours ($)",
            "market_cap": "Capitalisation ($)", "known_date": "Dernier dépôt SEC",
            "next_earnings_est": "Prochains résultats (estimés)", "flags": "Signalements"}
    t = live.sort_values([f"eligible_{dm}", f"rank_{dm}"], ascending=[False, True])
    out = t[[c for c in cols if c in t.columns]].rename(columns=cols)
    out.insert(0, "Ticker", t.index)
    for m in models:
        out[f"Motifs d'exclusion {labels[m]}"] = t[f"reason_text_{m}"].map(
            lambda r: " ; ".join(r or []))
    out.to_csv(SITE_DATA_DIR / "classement.csv", index=False, encoding="utf-8-sig")
    method = pd.DataFrame({"Méthode": [
        f"Classement au {pd.Timestamp(today).date()} - aide à la décision, pas un conseil.",
        "Score = moyenne pondérée des facteurs (rangs 0-100) ; pondérations par modèle :",
        *[f"  {labels[m]} : " + ", ".join(f"{FACTOR_LABELS[f]} {int(round(w * 100))} %"
                                          for f, w in C.model_weights(C.settings(), m).items()
                                          if w > 0) for m in models],
        "Fondamentaux : SEC EDGAR (XBRL), dernière version connue à chaque date.",
        "Cours : Yahoo Finance via yfinance (source non officielle).",
        "Banques, assureurs et immobilier exclus.",
    ]})
    with pd.ExcelWriter(SITE_DATA_DIR / "classement.xlsx", engine="openpyxl") as xw:
        out.to_excel(xw, sheet_name="Classement", index=False)
        for m in models:
            port = pd.DataFrame(blocks[m]["holdings"]).rename(columns={
                "ticker": "Ticker", "name": "Société", "sector": "Secteur", "entry_date": "Entrée",
                "return": "Rendement depuis l'entrée", "weight": "Poids", "rank": "Rang actuel",
                "score": "Score", "action": "À la prochaine revue",
                "sell_reason": "Motif de vente"})
            port.to_excel(xw, sheet_name=f"Portefeuille {m.upper()}", index=False)
        method.to_excel(xw, sheet_name="Méthode", index=False)


def snapshot_and_changes(live: pd.DataFrame, models: list[str], today) -> dict:
    d = HISTORY_DIR / "rankings"
    d.mkdir(parents=True, exist_ok=True)
    today = pd.Timestamp(today)
    cols = [c for m in models for c in (f"rank_{m}", f"composite_{m}", f"eligible_{m}")]
    snap = live[cols + FACTORS].copy()
    snap.index.name = "ticker"
    snap.round(2).to_csv(d / f"{today.date()}.csv")
    files = sorted(d.glob("*.csv"))
    for f in files:   # on garde les vendredis et les 10 derniers jours
        fd = pd.Timestamp(f.stem)
        if (today - fd).days > 10 and fd.weekday() != 4:
            f.unlink()
    files = sorted(d.glob("*.csv"))
    older = [f for f in files if pd.Timestamp(f.stem) <= today - pd.Timedelta(days=7)]
    ref_file = older[-1] if older else None
    if ref_file is None:
        return {"available": False, "as_of": today}
    prev = pd.read_csv(ref_file, index_col="ticker")
    out = {"available": True, "as_of": today, "compared_to": ref_file.stem, "models": {}}
    for m in models:
        rc = f"rank_{m}"
        if rc not in prev.columns:
            rc_prev = "rank" if "rank" in prev.columns and m == "v1" else None
        else:
            rc_prev = rc
        if rc_prev is None:
            continue
        cur_top = set(snap.index[snap[rc] <= 20])
        prev_top = set(prev.index[prev[rc_prev] <= 20])
        out["models"][m] = {"entered_top20": sorted(cur_top - prev_top),
                            "left_top20": sorted(prev_top - cur_top)}
    return out
