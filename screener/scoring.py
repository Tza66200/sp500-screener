"""Percentiles, scores par facteur, score global, filtres et classement."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .config import FACTORS
from .features import METRICS

FACTOR_METRICS = {f: [m for m, spec in METRICS.items() if spec[0] == f] for f in FACTORS}

REASONS = {
    "sector": "Secteur hors univers V1 (financières, immobilier)",
    "prices": "Historique de cours insuffisant (moins de 12 mois)",
    "sec": "Données SEC introuvables",
    "duplicate": "Autre catégorie d'actions de la même société",
    "stale": "Fondamentaux de plus de 6 mois",
    "insufficient": "Données insuffisantes (moins de 4 facteurs)",
    "liquidity": "Liquidité insuffisante",
    "trend": "Cours sous la moyenne mobile 200 jours",
    "merger": "Offre de rachat en cours",
    "veto": "Veto qualitatif",
}


def percentile(values: pd.Series, higher_better: bool) -> pd.Series:
    """Rang centré dans ]0, 100[ ; NaN conservés."""
    n = values.notna().sum()
    if n == 0:
        return values * np.nan
    pct = (values.rank(method="average") - 0.5) / n * 100
    return pct if higher_better else 100 - pct


def ranked(values: pd.Series, sectors: pd.Series, higher_better: bool, by_sector: bool,
           min_sector_size: int) -> pd.Series:
    overall = percentile(values, higher_better)
    if not by_sector:
        return overall
    g = values.groupby(sectors)
    n = g.transform("count")
    pct = (g.rank(method="average") - 0.5) / n * 100
    if not higher_better:
        pct = 100 - pct
    return pct.where(n >= min_sector_size, overall)


def base_exclusions(f: pd.DataFrame, settings: dict) -> pd.Series:
    """Raisons d'exclusion qui empêchent tout calcul (avant percentiles)."""
    reasons = pd.Series([[] for _ in range(len(f))], index=f.index, dtype=object)
    excluded = set(settings["universe"]["excluded_sectors"])
    for t in f.index:
        r = []
        if f.at[t, "sector"] in excluded:
            r.append("sector")
        mom = f.at[t, "mom_12_1"] if "mom_12_1" in f.columns else np.nan
        price = f.at[t, "price"] if "price" in f.columns else np.nan
        if pd.isna(mom) or pd.isna(price):
            r.append("prices")
        if pd.isna(f.at[t, "cik"]) or pd.isna(f.at[t, "known_date"]):
            r.append("sec")
        reasons.at[t] = r
    # Plusieurs catégories d'actions : on garde la plus liquide
    ok = reasons.map(len) == 0
    sub = f[ok & f["cik"].notna()]
    if len(sub):
        dv = sub["dollar_vol_63"].fillna(0)
        keep = dv.groupby(sub["cik"]).idxmax()
        for t in sub.index.difference(keep.values):
            reasons.at[t] = reasons.at[t] + ["duplicate"]
    return reasons


def score(f: pd.DataFrame, weights: dict, settings: dict) -> pd.DataFrame:
    """Calcule percentiles et scores sur l'univers classable (avant filtres)."""
    f = f.copy()
    sc = settings["scoring"]
    f["reasons"] = base_exclusions(f, settings)
    scorable = f["reasons"].map(len) == 0
    sectors = f["sector"].fillna("Inconnu")
    for m, (_, sign, by_sector) in METRICS.items():
        vals = f[m].where(scorable).astype(float) if m in f else pd.Series(np.nan, index=f.index)
        vals = vals.replace([np.inf, -np.inf], np.nan)
        f[f"pct_{m}"] = ranked(vals, sectors, sign > 0, by_sector, sc["min_sector_size"])
    for fac, metrics in FACTOR_METRICS.items():
        pcts = f[[f"pct_{m}" for m in metrics]]
        need = math.ceil(len(metrics) / 2)
        f[fac] = pcts.mean(axis=1).where(pcts.notna().sum(axis=1) >= need)
    f["n_metrics"] = f[[f"pct_{m}" for m in METRICS]].notna().sum(axis=1)
    f["data_confidence"] = (f["n_metrics"] / len(METRICS) * 100).round(0)
    f["composite"] = composite(f, weights, sc["min_factors"])
    return f


def composite(f: pd.DataFrame, weights: dict, min_factors: int) -> pd.Series:
    w = pd.Series(weights, dtype=float)
    scores = f[FACTORS]
    avail = scores.notna()
    wsum = (avail * w).sum(axis=1)
    total = (scores.fillna(0) * w).sum(axis=1) / wsum.where(wsum > 0)
    return total.where(avail.sum(axis=1) >= min_factors)


def apply_filters(f: pd.DataFrame, settings: dict, *, trend_filter: bool = False,
                  merger: dict | None = None, vetoes: dict | None = None) -> pd.DataFrame:
    """Ajoute les filtres éliminatoires, l'éligibilité et le rang parmi les éligibles."""
    f = f.copy()
    u = settings["universe"]
    reasons = f["reasons"].map(list)
    for t in f.index:
        r = reasons.at[t]
        if r:
            continue
        if f.at[t, "fundamentals_age_days"] > u["max_fundamentals_age_days"]:
            r.append("stale")
        if pd.isna(f.at[t, "composite"]):
            r.append("insufficient")
        if not (f.at[t, "dollar_vol_63"] >= u["min_dollar_volume_usd"]):
            r.append("liquidity")
        if trend_filter and not (f.at[t, "above_sma200"] == 1):
            r.append("trend")
        if merger and t in merger:
            r.append("merger")
        if vetoes and t in vetoes:
            r.append("veto")
    f["reasons"] = reasons
    f["eligible"] = reasons.map(len) == 0
    f["rank"] = f["composite"].where(f["eligible"]).rank(ascending=False, method="first")
    return f


def reason_text(codes: list[str], merger: dict | None = None, vetoes: dict | None = None,
                ticker: str | None = None) -> list[str]:
    out = []
    for c in codes:
        txt = REASONS.get(c, c)
        if c == "merger" and merger and ticker in merger:
            txt += f" ({merger[ticker]})"
        if c == "veto" and vetoes and ticker in vetoes:
            txt += f" : {vetoes[ticker]}"
        out.append(txt)
    return out
