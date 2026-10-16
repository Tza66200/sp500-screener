"""Backtest du portefeuille modèle et mesures de performance.

Hypothèses :
- Les scores sont calculés à la clôture du jour de revue avec les seules données disponibles
  ce jour-là ; les ordres sont exécutés à la clôture de la séance SUIVANTE.
- Coût : `cost_per_trade` appliqué à chaque dollar acheté ou vendu.
- Rendements dividendes réinvestis (cours ajustés Yahoo).
- Un titre dont les cotations s'arrêtent garde sa dernière valeur (équivalent à une sortie
  au dernier cours connu) jusqu'à la revue suivante.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .config import FACTORS
from .portfolio import review_decision
from .scoring import composite


@dataclass
class Result:
    name: str
    params: dict
    equity: pd.Series
    reviews: list[dict] = field(default_factory=list)
    positions: list[dict] = field(default_factory=list)      # positions clôturées
    turnover: list[tuple] = field(default_factory=list)       # (date, rotation aller simple)
    holdings: dict = field(default_factory=dict)              # positions ouvertes


def rank_frame(df: pd.DataFrame, params: dict, min_factors: int) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    out["sector"] = df["sector"]
    out["composite"] = composite(df, params["weights"], min_factors)
    elig = df["eligible_base"].astype(bool) & out["composite"].notna()
    if params.get("trend_filter"):
        elig &= df["above_sma200"] == 1
    out["eligible"] = elig
    out["rank"] = out["composite"].where(elig).rank(ascending=False, method="first")
    return out


def run(name: str, panel: dict, adj: pd.DataFrame, params: dict, reviews: list[pd.Timestamp],
        min_factors: int) -> Result:
    """Simulation quotidienne. `adj` : cours ajustés, déjà prolongés (ffill)."""
    cal = adj.index
    cols = {t: j for j, t in enumerate(adj.columns)}
    px = adj.values
    ratio = np.ones_like(px)
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio[1:] = px[1:] / px[:-1]
    ratio = np.where(np.isfinite(ratio), ratio, 1.0)
    review_pos = {cal.get_loc(r): r for r in reviews if r in panel}
    if not review_pos:
        raise ValueError("Aucune date de revue avec des scores")
    first = min(review_pos)
    cost_rate = params["cost_per_trade"]

    values: dict[str, float] = {}
    meta: dict[str, dict] = {}     # ticker -> {bought_review, entry_pos}
    cash = 1.0
    eq = np.full(len(cal), np.nan)
    res = Result(name=name, params=params, equity=pd.Series(dtype=float))
    pending = None
    review_idx = -1

    for i in range(first, len(cal)):
        if i > first:
            for t in values:
                values[t] *= ratio[i, cols[t]]
        if pending is not None and pending[0] == i:
            _, decision, rdate, ridx = pending
            total = cash + sum(values.values())
            target = decision.target
            tgt_val = total / len(target) if target else 0.0
            traded = sum(abs(tgt_val - values.get(t, 0.0)) for t in target)
            traded += sum(v for t, v in values.items() if t not in target)
            cost = traded * cost_rate
            total -= cost
            tgt_val = total / len(target) if target else 0.0
            for t in list(values):
                if t not in target:
                    m = meta.pop(t)
                    res.positions.append(_closed(t, m, i, px, cols, cal, decision.sell_reasons))
                    del values[t]
            for t in target:
                if t not in meta:
                    meta[t] = {"bought_review": ridx, "entry_pos": i}
                values[t] = tgt_val
            cash = total - tgt_val * len(target)
            res.turnover.append((cal[i], traded / 2 / (total + cost) if total > 0 else 0.0))
            res.reviews.append({"review_date": rdate, "executed": cal[i], "buy": decision.buy,
                                "sell": decision.sell, "sell_reasons": decision.sell_reasons,
                                "holdings": list(target), "cost": cost})
            pending = None
        eq[i] = cash + sum(values.values())
        if i in review_pos and i + 1 < len(cal):
            review_idx += 1
            scores = rank_frame(panel[review_pos[i]], params, min_factors)
            held = {t: m["bought_review"] for t, m in meta.items()}
            decision = review_decision(scores, held, params, review_idx)
            pending = (i + 1, decision, review_pos[i], review_idx)

    res.equity = pd.Series(eq, index=cal).dropna()
    for t, m in meta.items():
        res.holdings[t] = {"bought_review": m["bought_review"],
                           "entry_date": cal[m["entry_pos"]],
                           "entry_price": float(px[m["entry_pos"], cols[t]]),
                           "last_price": float(px[-1, cols[t]]),
                           "weight": values[t] / eq[len(cal) - 1]}
    return res


def _closed(t, m, i, px, cols, cal, reasons):
    p0, p1 = px[m["entry_pos"], cols[t]], px[i, cols[t]]
    return {"ticker": t, "entry": cal[m["entry_pos"]], "exit": cal[i],
            "return": float(p1 / p0 - 1) if p0 and np.isfinite(p0) and np.isfinite(p1) else None,
            "reason": reasons.get(t, "")}


# ----------------------------------------------------------------------------
# Mesures
# ----------------------------------------------------------------------------

def _cagr(e: pd.Series) -> float:
    years = (e.index[-1] - e.index[0]).days / 365.25
    return float((e.iloc[-1] / e.iloc[0]) ** (1 / years) - 1) if years > 0 else float("nan")


def metrics(res: Result, benches: dict[str, pd.Series], rf_daily: pd.Series,
            start: str, end: str | None) -> dict:
    e = res.equity.loc[start:end] if end else res.equity.loc[start:]
    if len(e) < 60:
        return {}
    r = e.pct_change().dropna()
    rf = rf_daily.reindex(r.index).ffill().fillna(0.0)
    vol = float(r.std() * math.sqrt(252))
    out = {
        "start": str(e.index[0].date()), "end": str(e.index[-1].date()),
        "cagr": _cagr(e), "volatility": vol,
        "sharpe": float((r - rf).mean() / r.std() * math.sqrt(252)) if r.std() > 0 else None,
        "max_drawdown": float((e / e.cummax() - 1).min()),
    }
    for key, b in benches.items():
        be = b.reindex(e.index).ffill()
        if be.isna().iloc[0]:
            continue
        br = be.pct_change().dropna()
        active = (r - br.reindex(r.index)).dropna()
        te = float(active.std() * math.sqrt(252))
        rel = (e / e.iloc[0]) / (be / be.iloc[0])
        out[f"bench_cagr_{key}"] = _cagr(be)
        out[f"excess_{key}"] = out["cagr"] - out[f"bench_cagr_{key}"]
        out[f"te_{key}"] = te
        out[f"ir_{key}"] = float(active.mean() * 252 / te) if te > 0 else None
        out[f"worst_12m_rel_{key}"] = float((rel / rel.shift(252) - 1).min()) \
            if len(rel) > 252 else None
    years = (e.index[-1] - e.index[0]).days / 365.25
    tov = [x for d, x in res.turnover if e.index[0] <= d <= e.index[-1]]
    out["turnover_per_year"] = float(sum(tov) / years) if years > 0 else None
    closed = [p for p in res.positions if p["return"] is not None
              and e.index[0] <= p["exit"] <= e.index[-1]]
    out["positions_closed"] = len(closed)
    out["hit_rate"] = float(np.mean([p["return"] > 0 for p in closed])) if closed else None
    return out


def weekly(series: pd.Series) -> pd.Series:
    """Dernière valeur de chaque semaine, datée du jour réel de cette valeur."""
    s = series.dropna()
    if s.empty:
        return s
    week = s.index.to_period("W-FRI")
    last = s.groupby(week).tail(1)
    return pd.concat([s.iloc[:1], last]).loc[lambda x: ~x.index.duplicated()]


def factor_returns_panel_check(panel: dict) -> None:  # pragma: no cover - aide au débogage
    for d, df in panel.items():
        missing = [f for f in FACTORS if f not in df]
        if missing:
            raise ValueError(f"{d}: facteurs manquants {missing}")
