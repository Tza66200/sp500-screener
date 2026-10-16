"""Analyse par facteur : corrélation de rang entre score et rendement futur."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .config import FACTORS

COLUMNS = FACTORS + ["composite"]


def ic_observations(panel: dict, adj: pd.DataFrame, horizons: list[int],
                    end_limit: pd.Timestamp, min_names: int = 30,
                    columns: list[str] | None = None) -> pd.DataFrame:
    """Une ligne par (date, horizon, facteur). Les rendements futurs ne dépassent pas end_limit."""
    cols = columns or COLUMNS
    cal = adj.index
    rows = []
    for d in sorted(panel):
        df = panel[d]
        df = df[df["scorable"]]
        if df.empty:
            continue
        p0 = cal.searchsorted(d, side="right") - 1
        for h in horizons:
            fwd = d + pd.DateOffset(months=h)
            if fwd > end_limit:
                continue
            p1 = cal.searchsorted(fwd, side="right") - 1
            tick = [t for t in df.index if t in adj.columns]
            ret = adj.iloc[p1][tick] / adj.iloc[p0][tick] - 1
            for f in cols:
                if f not in df:
                    continue
                s = df.loc[tick, f]
                ok = s.notna() & ret.notna()
                if ok.sum() < min_names:
                    continue
                ic = s[ok].rank().corr(ret[ok].rank())
                rows.append((d, h, f, float(ic), int(ok.sum())))
    return pd.DataFrame(rows, columns=["date", "horizon", "factor", "ic", "n"])


def summarize(obs: pd.DataFrame) -> list[dict]:
    out = []
    for (h, f), g in obs.groupby(["horizon", "factor"]):
        ic = g["ic"].dropna()
        n = len(ic)
        if n < 3:
            continue
        mean, std = float(ic.mean()), float(ic.std())
        out.append({
            "horizon": int(h), "factor": f, "mean_ic": mean, "std_ic": std, "n_months": n,
            "t_naive": mean / std * math.sqrt(n) if std > 0 else None,
            # chevauchement des fenêtres : environ n / h observations indépendantes
            "t_overlap_adj": mean / std * math.sqrt(max(n / h, 1)) if std > 0 else None,
            "pct_positive": float((ic > 0).mean()),
        })
    return out


def by_year(obs: pd.DataFrame, horizon: int = 12) -> list[dict]:
    g = obs[obs["horizon"] == horizon].copy()
    if g.empty:
        return []
    g["year"] = pd.to_datetime(g["date"]).dt.year
    t = g.pivot_table(index="year", columns="factor", values="ic", aggfunc="mean")
    return [{"year": int(y), **{f: (None if pd.isna(v) else float(v)) for f, v in row.items()}}
            for y, row in t.iterrows()]


def decay(obs: pd.DataFrame) -> list[dict]:
    t = obs.groupby(["factor", "horizon"])["ic"].mean().unstack("horizon")
    return [{"factor": f, **{str(int(h)): (None if pd.isna(v) else float(v))
                             for h, v in row.items()}} for f, row in t.iterrows()]


def success_rates(panel: dict, adj: pd.DataFrame, weights: dict, min_factors: int,
                  horizons: list[int], end_limit: pd.Timestamp, top_n: int = 20) -> list[dict]:
    """Taux de réussite du classement, cible « battre l'équipondéré de l'univers ».

    À chaque fin de mois : univers = titres éligibles classés par le modèle ; rendement futur
    de chacun (dividendes compris) ; moyenne équipondérée de l'univers. On compare :
    - le taux de base : part des titres de l'univers qui battent cette moyenne ;
    - le taux du top N : part des N premiers qui la battent ;
    - l'écart moyen du top N et de chaque quintile à cette moyenne.
    Classement brut, sans plafond sectoriel ni bande de tolérance."""
    from .scoring import composite

    cal = adj.index
    rows = []
    for d in sorted(panel):
        df = panel[d]
        comp = composite(df, weights, min_factors).where(df["eligible_base"])
        comp = comp.dropna()
        tick = [t for t in comp.index if t in adj.columns]
        if len(tick) < 5 * top_n:
            continue
        p0 = cal.searchsorted(d, side="right") - 1
        for h in horizons:
            fwd = d + pd.DateOffset(months=h)
            if fwd > end_limit:
                continue
            p1 = cal.searchsorted(fwd, side="right") - 1
            ret = (adj.iloc[p1][tick] / adj.iloc[p0][tick] - 1).dropna()
            if len(ret) < 5 * top_n:
                continue
            sc = comp.loc[ret.index]
            mean = ret.mean()
            order = sc.sort_values(ascending=False).index
            top = ret.loc[order[:top_n]]
            q = pd.qcut(sc.rank(method="first", ascending=False), 5, labels=False)
            qex = [float(ret[q == k].mean() - mean) for k in range(5)]
            rows.append({"date": d, "horizon": h, "base_rate": float((ret > mean).mean()),
                         "top_rate": float((top > mean).mean()),
                         "top_excess": float(top.mean() - mean),
                         **{f"q{k + 1}": qex[k] for k in range(5)}})
    if not rows:
        return []
    obs = pd.DataFrame(rows)
    out = []
    for h, g in obs.groupby("horizon"):
        n = len(g)
        spread = g["q1"] - g["q5"]
        sd = spread.std()
        out.append({
            "horizon": int(h), "n_months": n,
            "base_rate": float(g["base_rate"].mean()),
            "top_rate": float(g["top_rate"].mean()),
            "top_excess": float(g["top_excess"].mean()),
            "top_beats_universe_share": float((g["top_excess"] > 0).mean()),
            "quintiles": [float(g[f"q{k}"].mean()) for k in range(1, 6)],
            "spread": float(spread.mean()),
            "spread_t_overlap_adj": float(spread.mean() / sd * math.sqrt(max(n / h, 1)))
            if sd > 0 else None,
        })
    return out
