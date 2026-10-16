"""Analyse par facteur : corrélation de rang entre score et rendement futur."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .config import FACTORS

COLUMNS = FACTORS + ["composite"]


def ic_observations(panel: dict, adj: pd.DataFrame, horizons: list[int],
                    end_limit: pd.Timestamp, min_names: int = 30) -> pd.DataFrame:
    """Une ligne par (date, horizon, facteur). Les rendements futurs ne dépassent pas end_limit."""
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
            for f in COLUMNS:
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
