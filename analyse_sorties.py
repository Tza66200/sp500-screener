"""Analyse ponctuelle (branche temporaire) : règles de sortie alternatives.

Question : peut-on améliorer les ventes du portefeuille modèle (quand vendre, combien de
temps garder une ligne, comment rééquilibrer) ? Deux volets :

1. Diagnostic des ventes du site : rendement, sur les 3, 6 et 12 mois qui suivent chaque
   revue, des titres vendus, des titres achetés à leur place et des titres conservés, en
   écart au S&P 500 équipondéré. Si les titres vendus font aussi bien que ceux achetés, la
   règle de vente ne fait que tourner le portefeuille.
2. Variantes de sortie rejouées avec le moteur du site (classements de screener.scoring,
   règles de screener.portfolio), sur les données en cache (lecture seule).

Protocole, rédigé le 22/10/2026 AVANT toute exécution sur les données réelles
-----------------------------------------------------------------------------
La période réservée a déjà été révélée (17/10/2026) : aucune variante testée ici ne peut
être validée par le backtest seul. Pour limiter le risque de retenir un hasard :

1. Liste fermée de variantes (VARIANTES ci-dessous) : aucune n'est ajoutée, retirée ni
   réglée après lecture des résultats.
2. Chaque variante est jouée sur 6 cellules : 3 modèles (V1, V2, V3) x 2 calendriers de
   revue (celui du site et celui décalé d'un mois, déjà utilisé comme test de robustesse).
3. Variante de rendement « candidate » si, sur la période totale, elle bat la référence
   (rendement annualisé net de frais) dans au moins 5 cellules sur 6, si l'écart moyen est
   positif sur chacune des périodes 2011-2015, 2016-2020 et 2021 à aujourd'hui, et si la
   perte maximale moyenne ne se dégrade pas de plus de 3 points.
4. Variante de risque (stops, filtre de marché) « candidate » si le ratio de Sharpe
   progresse dans au moins 5 cellules sur 6 et si la perte maximale moyenne s'améliore
   d'au moins 3 points.
5. Les tranches ne sont pas jugées sur le rendement : elles mesurent et réduisent la part de
   chance liée aux dates de revue.
6. Une variante candidate n'est adoptée qu'après un suivi en parallèle (portefeuille
   fantôme) d'au moins 12 mois.

Mêmes conventions que le backtest du site : décision à la clôture du jour de revue, ordres à
la clôture suivante, 0,10 % de frais par transaction, dividendes réinvestis, mêmes limites
(sociétés sans cours absentes, pas de filtre d'offre de rachat dans l'historique). La
variante « reference » doit reproduire backtest.run à l'identique (verification.json).

Sorties dans resultats/ : resume.md, tableau.csv, comparaison.json, diagnostic_ventes.csv,
diagnostic_revues.csv, calendriers.csv, courbes.csv, verification.json.
"""
from __future__ import annotations

import bisect
import json
import logging
import os
import sys
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from screener import backtest as B  # noqa: E402
from screener import config as C  # noqa: E402
from screener import features as FT  # noqa: E402
from screener import pipeline as PL  # noqa: E402
from screener import prices as P  # noqa: E402
from screener import report as R  # noqa: E402
from screener import sec as SEC  # noqa: E402
from screener.portfolio import max_per_sector, review_dates, review_decision  # noqa: E402

log = logging.getLogger("analyse")
OUT = Path(os.environ.get("ANALYSE_OUT", "resultats"))
SLEEVES = ([1, 4, 7, 10], [2, 5, 8, 11], [3, 6, 9, 12])   # tranches décalées d'un mois
HORIZONS = (63, 126, 252)                                  # séances : environ 3, 6, 12 mois
MDD_TOLERANCE = 0.03
MDD_GAIN_RISK = 0.03


# ----------------------------------------------------------------------------
# Variantes (liste fermée, voir le protocole)
# ----------------------------------------------------------------------------

@dataclass(frozen=True)
class Rules:
    label: str
    family: str = "rendement"       # "reference", "rendement" ou "risque"
    hold_mult: float = 1.0          # seuil de conservation = hold_rank du site x hold_mult
    min_hold_days: int = 0          # pas de vente sur le rang avant ce délai (jours calendaires)
    hard_exit_mult: float = 0.0     # ... sauf si le rang dépasse hold_rank du site x ce facteur
    smooth: int = 0                 # rang lissé : n dernières fins de mois + jour de revue
    weighting: str = "equal"        # "equal" (site), "band" ou "drift"
    band: tuple = (0.5, 2.0)        # bande de non-intervention, en multiples du poids cible
    stop: str | None = None         # None, "trailing" ou "relative"
    stop_level: float = 0.0
    overlay: bool = False           # S&P 500 sous sa moyenne 10 mois -> bons du Trésor

    @property
    def site_rule(self) -> bool:
        return (self.hold_mult == 1.0 and not self.min_hold_days and not self.smooth
                and self.weighting == "equal" and not self.stop)


VARIANTES: dict[str, Rules] = {
    "reference": Rules("Règle du site : conserver tant que rang <= {h}, rééquilibrage à "
                       "poids égaux à chaque revue", family="reference"),
    "seuil_x1.5": Rules("Conserver tant que rang <= {h15}", hold_mult=1.5),
    "seuil_x2": Rules("Conserver tant que rang <= {h2}", hold_mult=2.0),
    "seuil_x3": Rules("Conserver tant que rang <= {h3}", hold_mult=3.0),
    "duree_6m": Rules("Pas de vente sur le rang avant 6 mois de détention, sauf rang > {h3}",
                      min_hold_days=175, hard_exit_mult=3.0),
    "duree_12m": Rules("Pas de vente sur le rang avant 12 mois de détention, sauf rang > {h3}",
                       min_hold_days=357, hard_exit_mult=3.0),
    "rang_lisse": Rules("Vente sur le rang moyen (3 dernières fins de mois + jour de revue)",
                        smooth=3),
    "bande": Rules("Rééquilibrage d'une ligne seulement hors de la bande 0,5x-2x le poids "
                   "cible", weighting="band"),
    "sans_reequilibrage": Rules("Lignes conservées jamais rééquilibrées", weighting="drift"),
    "stop_suiveur_25": Rules("Stop suiveur -25 % depuis le plus haut depuis l'achat, "
                             "remplacement immédiat", family="risque", stop="trailing",
                             stop_level=0.25),
    "stop_relatif_20": Rules("Stop relatif : retard de 20 % sur l'équipondéré depuis l'achat, "
                             "remplacement immédiat", family="risque", stop="relative",
                             stop_level=0.20),
    "combinaison": Rules("Conserver tant que rang <= {h2} + 6 mois minimum (sauf rang > {h3}) "
                         "+ bande 0,5x-2x", hold_mult=2.0, min_hold_days=175,
                         hard_exit_mult=3.0, weighting="band"),
    "filtre_marche": Rules("Règle du site + bons du Trésor quand le S&P 500 finit le mois sous "
                           "sa moyenne 10 mois", family="risque", overlay=True),
}
TRANCHE_VARIANTS = ("reference", "combinaison")


# ----------------------------------------------------------------------------
# Marché
# ----------------------------------------------------------------------------

class Market:
    """Cours ajustés prolongés (comme le backtest du site), taux sans risque, indices."""

    def __init__(self, adj: pd.DataFrame, rf_daily: pd.Series, ew_symbol: str,
                 sp_symbol: str):
        self.cal = adj.index
        self.cols = {t: j for j, t in enumerate(adj.columns)}
        self.px = adj.values
        ratio = np.ones_like(self.px)
        with np.errstate(invalid="ignore", divide="ignore"):
            ratio[1:] = self.px[1:] / self.px[:-1]
        self.ratio = np.where(np.isfinite(ratio), ratio, 1.0)
        self.rf = rf_daily.reindex(self.cal).ffill().fillna(0.0).to_numpy(dtype=float)
        self.ew = self.px[:, self.cols[ew_symbol]] if ew_symbol in self.cols else None
        self.sp = self.px[:, self.cols[sp_symbol]] if sp_symbol in self.cols else None

    def fwd(self, t: str, i: int, h: int) -> float:
        j = self.cols.get(t)
        if j is None or i + h >= len(self.cal):
            return np.nan
        a, b = self.px[i, j], self.px[i + h, j]
        return float(b / a - 1) if np.isfinite(a) and np.isfinite(b) and a > 0 else np.nan

    def fwd_ew(self, i: int, h: int) -> float:
        if self.ew is None or i + h >= len(self.cal):
            return np.nan
        return float(self.ew[i + h] / self.ew[i] - 1)


# ----------------------------------------------------------------------------
# Décisions
# ----------------------------------------------------------------------------

def decide(scores: pd.DataFrame, meta: dict, params: dict, rules: Rules, hold_rank: float,
           when: pd.Timestamp, smooth: dict | None = None):
    """Comme portfolio.review_decision (mode « band »), avec le seuil, la durée minimale et
    le rang lissé de la variante. Renvoie (keep, buy, sell_reasons)."""
    n = params["n_positions"]
    cap = max_per_sector(params)
    eligible = scores[scores["eligible"]].sort_values("rank")
    keep, reasons = [], {}
    for t, m in meta.items():
        if t not in eligible.index:
            reasons[t] = "n'est plus éligible"
            continue
        rank = eligible.at[t, "rank"]
        eff = smooth.get(t, rank) if smooth is not None else rank
        young = rules.min_hold_days and (when - m["entry_date"]).days < rules.min_hold_days
        hard = rules.hard_exit_mult and rank > params["hold_rank"] * rules.hard_exit_mult
        if young and not hard:
            keep.append(t)
        elif eff <= hold_rank:
            keep.append(t)
        else:
            reasons[t] = f"rang {int(rank)}" + (f" (lissé {eff:.0f})" if smooth is not None
                                                else "")
    count: dict[str, int] = {}
    for t in keep:
        s = eligible.at[t, "sector"]
        count[s] = count.get(s, 0) + 1
    buy = []
    for t, row in eligible.iterrows():
        if len(keep) + len(buy) >= n:
            break
        if t in keep:
            continue
        s = row["sector"]
        if count.get(s, 0) >= cap:
            continue
        buy.append(t)
        count[s] = count.get(s, 0) + 1
    return keep, buy, reasons


def smoothed_ranks(rdate: pd.Timestamp, scores: pd.DataFrame, ranks: dict,
                   month_ends: list, k: int) -> dict:
    """Rang moyen sur les k dernières fins de mois avant la revue et le jour de revue ; un
    titre absent ou inéligible à une date prend le pire rang de cette date."""
    j = bisect.bisect_left(month_ends, rdate)
    frames = [ranks[d] for d in month_ends[max(0, j - k):j]] + [scores]
    cols = []
    for f in frames:
        el = f["eligible"].astype(bool)
        cols.append((f["rank"].where(el), float(el.sum() + 1)))
    df = pd.concat([c for c, _ in cols], axis=1, keys=range(len(cols)))
    for c, (_, worst) in zip(df.columns, cols):
        df[c] = df[c].fillna(worst)
    return df.mean(axis=1).to_dict()


def target_weights(values: dict, keep: list, buy: list, total: float, rules: Rules) -> dict:
    target = keep + buy
    w_star = 1.0 / len(target)
    lo, hi = rules.band
    w = {}
    for t in target:
        cur = values.get(t, 0.0) / total if total > 0 else 0.0
        if t in values and (rules.weighting == "drift" or lo * w_star <= cur <= hi * w_star):
            w[t] = cur
        else:
            w[t] = w_star
    s = sum(w.values())
    return {t: x / s for t, x in w.items()}


def new_meta(mk: Market, t: str, i: int, ridx: int, scores: pd.DataFrame) -> dict:
    p = float(mk.px[i, mk.cols[t]])
    return {"bought_review": ridx, "entry_pos": i, "entry_date": mk.cal[i], "entry_price": p,
            "peak": p, "entry_ew": float(mk.ew[i]) if mk.ew is not None else np.nan,
            "sector": scores.at[t, "sector"] if t in scores.index else None}


def closed(mk: Market, t: str, m: dict, i: int, reason: str, kind: str) -> dict:
    """Même calcul que backtest._closed."""
    p0, p1 = mk.px[m["entry_pos"], mk.cols[t]], mk.px[i, mk.cols[t]]
    ok = bool(p0) and np.isfinite(p0) and np.isfinite(p1)
    return {"ticker": t, "entry": mk.cal[m["entry_pos"]], "exit": mk.cal[i],
            "return": float(p1 / p0 - 1) if ok else None, "reason": reason, "kind": kind}


def stop_hits(mk: Market, meta: dict, values: dict, i: int, rules: Rules) -> list[str]:
    hits = []
    for t in values:
        m = meta[t]
        p = mk.px[i, mk.cols[t]]
        if not (np.isfinite(p) and np.isfinite(m["entry_price"]) and m["entry_price"] > 0):
            continue
        if rules.stop == "trailing":
            dd = p / m["peak"] - 1.0
        else:
            if mk.ew is None or not np.isfinite(m["entry_ew"]):
                continue
            dd = (p / m["entry_price"]) / (mk.ew[i] / m["entry_ew"]) - 1.0
        if dd <= -rules.stop_level:
            hits.append(t)
    return hits


def replacements(scores: pd.DataFrame, meta: dict, exclude: set, params: dict) -> list[str]:
    cap = max_per_sector(params)
    slots = params["n_positions"] - len(meta)
    count: dict = {}
    for m in meta.values():
        count[m["sector"]] = count.get(m["sector"], 0) + 1
    out = []
    for t, row in scores[scores["eligible"]].sort_values("rank").iterrows():
        if len(out) >= slots:
            break
        if t in meta or t in exclude:
            continue
        if count.get(row["sector"], 0) >= cap:
            continue
        out.append(t)
        count[row["sector"]] = count.get(row["sector"], 0) + 1
    return out


# ----------------------------------------------------------------------------
# Simulation
# ----------------------------------------------------------------------------

def simulate(name: str, mk: Market, ranks: dict, params: dict, reviews: list, rules: Rules,
             month_ends: list) -> B.Result:
    """Simulation quotidienne. Avec la règle du site, reproduit backtest.run à l'identique."""
    cal, cols, ratio, px = mk.cal, mk.cols, mk.ratio, mk.px
    review_pos = {cal.get_loc(r): r for r in reviews if r in ranks}
    if not review_pos:
        raise ValueError("Aucune date de revue avec des classements")
    first = min(review_pos)
    rate = params["cost_per_trade"]
    hold_rank = params["hold_rank"] * rules.hold_mult
    rank_dates = sorted(ranks)
    values: dict[str, float] = {}
    meta: dict[str, dict] = {}
    cash = 1.0
    eq = np.full(len(cal), np.nan)
    res = B.Result(name=name, params=params, equity=pd.Series(dtype=float))
    res.costs, res.stops, res.max_weight, res.review_log = [], [], [], []
    pending = None
    review_idx = -1

    for i in range(first, len(cal)):
        if i > first:
            for t in values:
                values[t] *= ratio[i, cols[t]]
            if rules.stop:
                if abs(cash) > 1e-12:
                    cash *= 1.0 + mk.rf[i]
                for t in values:
                    p = px[i, cols[t]]
                    if p > meta[t]["peak"]:
                        meta[t]["peak"] = p
        if pending is not None and pending[0] == i:
            if pending[1] == "revue":
                _, _, keep, buy, reasons, rdate, ridx, scores = pending
                target = keep + buy
                pre = cash + sum(values.values())
                total = pre
                pre_max = max(values.values()) / pre if values and pre > 0 else 0.0
                if rules.weighting == "equal":
                    weights = None
                    tgt_val = total / len(target) if target else 0.0
                    traded = sum(abs(tgt_val - values.get(t, 0.0)) for t in target)
                    traded += sum(v for t, v in values.items() if t not in target)
                    cost = traded * rate
                    total -= cost
                    tgt_val = total / len(target) if target else 0.0
                else:
                    weights = target_weights(values, keep, buy, total, rules)
                    traded = sum(abs(weights[t] * total - values.get(t, 0.0)) for t in target)
                    traded += sum(v for t, v in values.items() if t not in target)
                    cost = traded * rate
                    total -= cost
                sold = []
                for t in list(values):
                    if t not in target:
                        m = meta.pop(t)
                        res.positions.append(closed(mk, t, m, i, reasons.get(t, ""), "revue"))
                        sold.append(t)
                        del values[t]
                for t in target:
                    if t not in meta:
                        meta[t] = new_meta(mk, t, i, ridx, scores)
                    values[t] = tgt_val if weights is None else weights[t] * total
                if weights is None:
                    cash = total - tgt_val * len(target)
                else:
                    cash = total - sum(values[t] for t in target)
                res.turnover.append((cal[i], traded / 2 / (total + cost) if total > 0 else 0.0))
                res.costs.append((cal[i], cost / pre if pre > 0 else 0.0))
                post = cash + sum(values.values())
                res.max_weight.append((cal[i], max(values.values()) / post if values else 0.0,
                                       pre_max))
                res.reviews.append({"review_date": rdate, "executed": cal[i], "buy": buy,
                                    "sell": sold, "sell_reasons": reasons,
                                    "holdings": list(target), "cost": cost})
                el = scores[scores["eligible"]]
                res.review_log.append({
                    "decision": rdate, "pos": i, "keep": list(keep), "buy": list(buy),
                    "sell": sold, "reasons": dict(reasons),
                    "rank": {t: float(el.at[t, "rank"]) for t in sold + keep if t in el.index}})
            else:
                _, _, hits, decided, ridx = pending
                pre = cash + sum(values.values())
                proceeds = 0.0
                for t in hits:
                    if t not in values:
                        continue
                    m = meta.pop(t)
                    res.positions.append(closed(mk, t, m, i, "stop", "stop"))
                    proceeds += values.pop(t)
                cost = proceeds * rate
                cash += proceeds - cost
                k = bisect.bisect_right(rank_dates, decided) - 1
                sc = ranks[rank_dates[k]]
                buys = replacements(sc, meta, set(hits), params)
                spend = 0.0
                if buys and cash > 1e-12:
                    spend = cash / (1 + rate)
                    cost += spend * rate
                    each = spend / len(buys)
                    for t in buys:
                        values[t] = each
                        meta[t] = new_meta(mk, t, i, ridx, sc)
                    cash = 0.0
                res.turnover.append((cal[i], (proceeds + spend) / 2 / pre if pre > 0 else 0.0))
                res.costs.append((cal[i], cost / pre if pre > 0 else 0.0))
                res.stops.append({"date": cal[i], "sold": list(hits), "bought": buys})
            pending = None
        eq[i] = cash + sum(values.values())
        if i + 1 >= len(cal):
            continue
        if i in review_pos:
            review_idx += 1
            rdate = review_pos[i]
            scores = ranks[rdate]
            smooth = smoothed_ranks(rdate, scores, ranks, month_ends, rules.smooth) \
                if rules.smooth else None
            keep, buy, reasons = decide(scores, meta, params, rules, hold_rank, rdate, smooth)
            pending = (i + 1, "revue", keep, buy, reasons, rdate, review_idx, scores)
        elif rules.stop and pending is None and values:
            hits = stop_hits(mk, meta, values, i, rules)
            if hits:
                pending = (i + 1, "stop", hits, cal[i], review_idx)

    res.equity = pd.Series(eq, index=cal).dropna()
    last = len(cal) - 1
    for t, m in meta.items():
        res.holdings[t] = {"entry_date": m["entry_date"],
                           "weight": values[t] / eq[last] if eq[last] else None}
    return res


def with_overlay(res: B.Result, mk: Market, params: dict, month_end_pos: list[int]) -> B.Result:
    """Filtre de tendance du marché appliqué à la courbe : à chaque fin de mois, si le S&P 500
    (dividendes réinvestis) clôture sous la moyenne de ses 10 dernières clôtures de fin de
    mois, tout passe en bons du Trésor à la clôture suivante ; retour dans le portefeuille
    (qui a continué de vivre) dès qu'il repasse au-dessus. Frais de bascule : 0,10 %."""
    out = B.Result(name=res.name + ":filtre", params=params, equity=pd.Series(dtype=float))
    if mk.sp is None:
        out.equity = res.equity.copy()
        return out
    rate = params["cost_per_trade"]
    closes = mk.sp[month_end_pos]
    signal = {}
    for k, p in enumerate(month_end_pos):
        window = closes[max(0, k - 9):k + 1]
        signal[p] = True if k < 9 else bool(closes[k] >= np.nanmean(window))
    e = res.equity
    idx = mk.cal.get_indexer(e.index)
    r = e.pct_change().fillna(0.0).to_numpy()
    prior = [p for p in month_end_pos if p <= idx[0]]
    inside = signal[prior[-1]] if prior else True
    v = float(e.iloc[0])
    vals = [v]
    switch_at, switches, inside_flags = None, [], [inside]
    for k in range(1, len(e)):
        pos = idx[k]
        v *= 1.0 + (r[k] if inside else mk.rf[pos])
        if switch_at == pos:
            v *= 1.0 - rate
            inside = not inside
            switches.append(mk.cal[pos])
            switch_at = None
        if pos in signal and signal[pos] != inside and switch_at is None and pos + 1 < len(mk.cal):
            switch_at = pos + 1
        vals.append(v)
        inside_flags.append(inside)
    out.equity = pd.Series(vals, index=e.index)
    flags = pd.Series(inside_flags, index=e.index)
    out.turnover = [(d, x * float(flags.asof(d))) for d, x in res.turnover] + \
                   [(d, 1.0) for d in switches]
    out.positions = res.positions
    out.costs = [(d, c * float(flags.asof(d))) for d, c in res.costs] + \
                [(d, rate) for d in switches]
    out.stops, out.max_weight, out.reviews = [], res.max_weight, res.reviews
    out.switches = switches
    out.time_inside = float(flags.mean())
    return out


def run_tranches(name: str, mk: Market, ranks: dict, params: dict, sleeve_reviews: list,
                 rules: Rules, month_ends: list) -> tuple[B.Result, list[B.Result]]:
    """Trois portefeuilles d'un tiers chacun, revus à des mois décalés. Avant sa première
    revue, une tranche attend en bons du Trésor."""
    sleeves = [simulate(f"{name}:t{k + 1}", mk, ranks, params, revs, rules, month_ends)
               for k, revs in enumerate(sleeve_reviews)]
    cal = mk.cal
    i0 = min(cal.get_loc(s.equity.index[0]) for s in sleeves)
    idx = cal[i0:]
    parts = []
    for s in sleeves:
        i_s = cal.get_loc(s.equity.index[0])
        growth = np.cumprod(np.r_[1.0, 1.0 + mk.rf[i0 + 1:i_s + 1]])     # i0 .. i_s
        v = np.empty(len(idx))
        v[:i_s - i0 + 1] = growth / 3.0
        e = s.equity.to_numpy()
        v[i_s - i0:] = growth[-1] / 3.0 * e / e[0]
        parts.append(pd.Series(v, index=idx))
    total = sum(parts)
    out = B.Result(name=name, params=params, equity=total)
    share = [p / total for p in parts]
    out.turnover = [(d, x * float(sh.asof(d))) for s, sh in zip(sleeves, share)
                    for d, x in s.turnover]
    out.costs = [(d, c * float(sh.asof(d))) for s, sh in zip(sleeves, share) for d, c in s.costs]
    out.positions = [p for s in sleeves for p in s.positions]
    out.stops = []
    out.max_weight = []
    out.reviews = [rv for s in sleeves for rv in s.reviews]
    out.all_invested = max(s.equity.index[0] for s in sleeves)
    return out, sleeves


# ----------------------------------------------------------------------------
# Mesures
# ----------------------------------------------------------------------------

def extra_stats(res: B.Result, start, end) -> dict:
    s = pd.Timestamp(start)
    e = pd.Timestamp(end) if end else res.equity.index[-1]
    eqs = res.equity.loc[s:e]
    if len(eqs) < 60:
        return {}
    years = (eqs.index[-1] - eqs.index[0]).days / 365.25
    closed_p = [p for p in res.positions if s <= p["exit"] <= e]
    days = [(p["exit"] - p["entry"]).days for p in closed_p]
    costs = sum(c for d, c in getattr(res, "costs", []) if s <= d <= e)
    stops = [x for x in getattr(res, "stops", []) if s <= x["date"] <= e]
    mw = [x for x in getattr(res, "max_weight", []) if s <= x[0] <= e]
    return {
        "ventes_par_an": len(closed_p) / years if years > 0 else None,
        "duree_mediane_jours": float(np.median(days)) if days else None,
        "duree_moyenne_jours": float(np.mean(days)) if days else None,
        "part_detenue_12m_plus": float(np.mean([d >= 365 for d in days])) if days else None,
        "frais_par_an": costs / years if years > 0 else None,
        "stops_par_an": sum(len(x["sold"]) for x in stops) / years if years > 0 else None,
        "poids_max_moyen": float(np.mean([x[1] for x in mw])) if mw else None,
        "poids_max_avant_revue": float(np.max([x[2] for x in mw])) if mw else None,
    }


def all_metrics(res: B.Result, bench: dict, rf_daily: pd.Series, periods: dict) -> dict:
    out = {}
    for p, (a, b) in periods.items():
        a = max(pd.Timestamp(a), res.equity.index[0])
        m = B.metrics(res, bench, rf_daily, str(a.date()), b)
        if m:
            m.update(extra_stats(res, a, b))
        out[p] = m
    return out


def sale_diagnostics(res: B.Result, mk: Market, ranks: dict, params: dict, tags: dict
                     ) -> tuple[list[dict], list[dict]]:
    """Rendement après la revue des titres vendus, achetés et conservés."""
    hold = params["hold_rank"]
    n = params["n_positions"]
    per_sale, per_review = [], []
    log_ = res.review_log
    for k, rv in enumerate(log_):
        e = rv["pos"]
        nxt = ranks.get(log_[k + 1]["decision"]) if k + 1 < len(log_) else None
        row_r = {**tags, "decision": rv["decision"].date(), "ventes": len(rv["sell"]),
                 "achats": len(rv["buy"]), "conserves": len(rv["keep"])}
        for h in HORIZONS:
            ew = mk.fwd_ew(e, h)
            for grp in ("sell", "buy", "keep"):
                vals = [mk.fwd(t, e, h) for t in rv[grp]]
                vals = [v for v in vals if np.isfinite(v)]
                row_r[f"{grp}_{h}"] = float(np.mean(vals)) - ew if vals and np.isfinite(ew) \
                    else None
        per_review.append(row_r)
        for t in rv["sell"]:
            back50 = back20 = None
            if nxt is not None:
                ok = t in nxt.index and bool(nxt.at[t, "eligible"])
                back50 = bool(ok and nxt.at[t, "rank"] <= hold)
                back20 = bool(ok and nxt.at[t, "rank"] <= n)
            row = {**tags, "decision": rv["decision"].date(), "ticker": t,
                   "motif": rv["reasons"].get(t, ""), "rang": rv["rank"].get(t),
                   "dans_top_conservation_revue_suivante": back50,
                   "dans_top_n_revue_suivante": back20}
            for h in HORIZONS:
                r, ew = mk.fwd(t, e, h), mk.fwd_ew(e, h)
                row[f"exces_{h}"] = r - ew if np.isfinite(r) and np.isfinite(ew) else None
                row[f"achats_exces_{h}"] = row_r[f"buy_{h}"]
            per_sale.append(row)
    return per_sale, per_review


def summarize_sales(per_sale: list[dict], per_review: list[dict], hold: int) -> dict:
    out = {}
    s = pd.DataFrame(per_sale)
    r = pd.DataFrame(per_review)
    if s.empty or r.empty:
        return out
    for model, g in r.groupby("modele"):
        block = {}
        for h in HORIZONS:
            sub = g.dropna(subset=[f"sell_{h}", f"buy_{h}"])
            if sub.empty:
                continue
            gap = sub[f"buy_{h}"] - sub[f"sell_{h}"]
            block[h] = {
                "revues": int(len(sub)),
                "vendus_exces_moyen": float(sub[f"sell_{h}"].mean()),
                "achetes_exces_moyen": float(sub[f"buy_{h}"].mean()),
                "conserves_exces_moyen": float(sub[f"keep_{h}"].dropna().mean()),
                "achetes_moins_vendus_moyen": float(gap.mean()),
                "achetes_moins_vendus_t": float(gap.mean() / gap.std() * np.sqrt(len(gap)))
                if len(gap) > 2 and gap.std() > 0 else None,
                "revues_achetes_meilleurs_part": float((gap > 0).mean()),
            }
        out[model] = {"horizons": block}
        sm = s[s["modele"] == model]
        bins = [hold, hold * 1.5, hold * 2, hold * 3, np.inf]
        labels = [f"{int(bins[i]) + 1}-{int(bins[i + 1])}" if np.isfinite(bins[i + 1])
                  else f"> {int(bins[i])}" for i in range(len(bins) - 1)]
        sm = sm.assign(tranche=pd.cut(sm["rang"], bins, labels=labels))
        sm.loc[sm["rang"].isna(), "tranche"] = np.nan
        rows = []
        for lab, gg in sm.groupby("tranche", observed=True):
            row = {"tranche_de_rang": str(lab), "ventes": int(len(gg))}
            for h in HORIZONS:
                v = gg[f"exces_{h}"].dropna()
                row[f"exces_moyen_{h}"] = float(v.mean()) if len(v) else None
                row[f"exces_median_{h}"] = float(v.median()) if len(v) else None
                row[f"bat_equipondere_{h}"] = float((v > 0).mean()) if len(v) else None
            rows.append(row)
        inel = sm[sm["rang"].isna()]
        if len(inel):
            row = {"tranche_de_rang": "plus éligible", "ventes": int(len(inel))}
            for h in HORIZONS:
                v = inel[f"exces_{h}"].dropna()
                row[f"exces_moyen_{h}"] = float(v.mean()) if len(v) else None
            rows.append(row)
        out[model]["par_rang"] = rows
        b = sm["dans_top_conservation_revue_suivante"].dropna()
        out[model]["retour_top_conservation_revue_suivante"] = float(b.mean()) if len(b) else None
        b = sm["dans_top_n_revue_suivante"].dropna()
        out[model]["retour_top_n_revue_suivante"] = float(b.mean()) if len(b) else None
    return out


def verdicts(table: pd.DataFrame, models: list, schedules: list) -> list[dict]:
    """Applique les règles 3 et 4 du protocole."""
    out = []
    ref = table[table["variante"] == "reference"].set_index(["modele", "calendrier", "periode"])
    for v, rules in VARIANTES.items():
        if v == "reference":
            continue
        sub = table[table["variante"] == v].set_index(["modele", "calendrier", "periode"])
        cells = [(m, s) for m in models for s in schedules]

        def diff(col, period):
            d = []
            for m, s in cells:
                key = (m, s, period)
                if key in sub.index and key in ref.index:
                    a, b = sub.at[key, col], ref.at[key, col]
                    if pd.notna(a) and pd.notna(b):
                        d.append(float(a) - float(b))
            return d

        tot = diff("cagr", "totale")
        if not tot:
            continue
        row = {"variante": v, "libelle": rules.label, "famille": rules.family,
               "cellules": len(tot), "cellules_gagnantes": int(sum(x > 0 for x in tot)),
               "ecart_cagr_totale": float(np.mean(tot))}
        for p in ("2011-2015", "2016-2020", "reservee"):
            d = diff("cagr", p)
            row[f"ecart_cagr_{p}"] = float(np.mean(d)) if d else None
        dd = diff("max_drawdown", "totale")
        row["ecart_perte_max"] = float(np.mean(dd)) if dd else None
        sh = diff("sharpe", "totale")
        row["ecart_sharpe"] = float(np.mean(sh)) if sh else None
        row["cellules_sharpe_meilleur"] = int(sum(x > 0 for x in sh))
        for col in ("ventes_par_an", "duree_mediane_jours", "frais_par_an",
                    "poids_max_avant_revue"):
            vals = sub.xs("totale", level="periode")[col].dropna()
            row[col] = float(vals.mean()) if len(vals) else None
        need = 5 if len(tot) == 6 else max(1, len(tot) - 1)
        if rules.family == "risque":
            ok = row["cellules_sharpe_meilleur"] >= need and \
                (row["ecart_perte_max"] or 0) >= MDD_GAIN_RISK
        else:
            periods_ok = all((row.get(f"ecart_cagr_{p}") or -1) > 0
                             for p in ("2011-2015", "2016-2020", "reservee"))
            ok = row["cellules_gagnantes"] >= need and periods_ok and \
                (row["ecart_perte_max"] or 0) >= -MDD_TOLERANCE
        row["verdict"] = "candidate" if ok else "rejetée"
        out.append(row)
    return out


# ----------------------------------------------------------------------------
# Rapport lisible
# ----------------------------------------------------------------------------

def pct(x, digits=1, plus=True):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "–"
    return R.fr(100 * x, digits, plus) + " %"


def num(x, digits=1):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "–"
    return R.fr(x, digits, False)


def write_summary(path: Path, ctx: dict) -> None:
    L = []
    a = L.append
    a("# Analyse ponctuelle des règles de sortie\n")
    a(f"Données jusqu'au {ctx['data_end']}. Début du backtest : {ctx['start']}. "
      f"Frais : {pct(ctx['cost'], 2, False)} par transaction. Seuil de conservation du site : "
      f"rang {ctx['hold']}, {ctx['n']} lignes.\n")
    a("Protocole fixé le 22/10/2026 avant exécution (voir l'en-tête d'analyse_sorties.py). "
      "La période réservée étant déjà révélée, ces résultats ne valent pas validation : une "
      "variante « candidate » doit encore passer 12 mois de suivi en parallèle.\n")
    a("## 1. Vérification\n")
    for k, v in ctx["verification"].items():
        a(f"- {k} : {v}")
    a("")
    a("## 2. Que rapportent les ventes du site ?\n")
    a("Rendement après la revue, en écart au S&P 500 équipondéré, moyenne par revue "
      "(calendrier du site, règle du site).\n")
    a("| Modèle | Horizon | Vendus | Achetés | Conservés | Achetés − vendus | t | "
      "Revues où les achats battent les ventes |")
    a("|---|---|---|---|---|---|---|---|")
    for m, blk in ctx["sales"].items():
        for h, x in blk["horizons"].items():
            a(f"| {m.upper()} | {h} séances | {pct(x['vendus_exces_moyen'])} | "
              f"{pct(x['achetes_exces_moyen'])} | {pct(x['conserves_exces_moyen'])} | "
              f"{pct(x['achetes_moins_vendus_moyen'])} | {num(x['achetes_moins_vendus_t'])} | "
              f"{pct(x['revues_achetes_meilleurs_part'], 0, False)} |")
    a("")
    a("Titres vendus selon leur rang le jour de la vente (écart moyen à l'équipondéré "
      "sur les 6 et 12 mois suivants) :\n")
    a("| Modèle | Rang à la vente | Ventes | 6 mois | 12 mois | Battent l'équipondéré à 12 mois |")
    a("|---|---|---|---|---|---|")
    for m, blk in ctx["sales"].items():
        for r in blk["par_rang"]:
            a(f"| {m.upper()} | {r['tranche_de_rang']} | {r['ventes']} | "
              f"{pct(r.get('exces_moyen_126'))} | {pct(r.get('exces_moyen_252'))} | "
              f"{pct(r.get('bat_equipondere_252'), 0, False)} |")
    a("")
    for m, blk in ctx["sales"].items():
        a(f"- {m.upper()} : {pct(blk['retour_top_conservation_revue_suivante'], 0, False)} des "
          f"titres vendus sont de retour dans le top {ctx['hold']} à la revue suivante, "
          f"{pct(blk['retour_top_n_revue_suivante'], 0, False)} dans le top {ctx['n']}.")
    a("")
    a("## 3. Variantes : écart à la référence\n")
    a("Moyenne sur 6 cellules (3 modèles x 2 calendriers). Écarts de rendement annualisé net "
      "de frais, en points ; perte maximale : un écart positif est une amélioration.\n")
    a("| Variante | Famille | Cellules gagnantes | Totale | 2011-2015 | 2016-2020 | 2021+ | "
      "Perte max | Sharpe | Ventes/an | Durée médiane (j) | Verdict |")
    a("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in ctx["verdicts"]:
        a(f"| {r['variante']} | {r['famille']} | {r['cellules_gagnantes']}/{r['cellules']} | "
          f"{pct(r['ecart_cagr_totale'], 2)} | {pct(r.get('ecart_cagr_2011-2015'), 2)} | "
          f"{pct(r.get('ecart_cagr_2016-2020'), 2)} | {pct(r.get('ecart_cagr_reservee'), 2)} | "
          f"{pct(r.get('ecart_perte_max'))} | {num(r.get('ecart_sharpe'), 2)} | "
          f"{num(r.get('ventes_par_an'))} | {num(r.get('duree_mediane_jours'), 0)} | "
          f"{r['verdict']} |")
    a("")
    a("Libellés :\n")
    for v, rules in VARIANTES.items():
        a(f"- `{v}` : {ctx['labels'][v]}")
    a("")
    a("## 4. Détail : rendement annualisé, période totale\n")
    cols = [(m, s) for m in ctx["models"] for s in ctx["schedules"]]
    a("| Variante | " + " | ".join(f"{m.upper()} {s}" for m, s in cols) + " |")
    a("|---|" + "---|" * len(cols))
    t = ctx["table"]
    for v in VARIANTES:
        cells = []
        for m, s in cols:
            x = t[(t.variante == v) & (t.modele == m) & (t.calendrier == s) &
                  (t.periode == "totale")]["cagr"]
            cells.append(pct(float(x.iloc[0]), 2, False) if len(x) and pd.notna(x.iloc[0])
                         else "–")
        a(f"| {v} | " + " | ".join(cells) + " |")
    a("")
    a("## 5. Chance du calendrier et tranches\n")
    a(f"Règle du site, même fenêtre pour tous (à partir du {ctx['common_start']}, quand les "
      "trois tranches sont investies). Rendement annualisé.\n")
    cal_rows = ctx["calendars"]
    a("| Calendrier | " + " | ".join(m.upper() for m in ctx["models"]) + " |")
    a("|---|" + "---|" * len(ctx["models"]))
    for name, vals in cal_rows.items():
        a(f"| {name} | " + " | ".join(pct(vals.get(m), 2, False) for m in ctx["models"]) + " |")
    a("")
    a("## Limites\n")
    a("- Période réservée déjà révélée : ces écarts sont des indices, pas des preuves.")
    a("- Sociétés sans cours Yahoo absentes (biais de survivance, voir l'onglet Données).")
    a("- Stops : décision à la clôture, exécution à la clôture suivante ; les écarts "
      "d'ouverture et l'élargissement des fourchettes en cas de chute ne sont pas modélisés, "
      "ce qui avantage les stops.")
    a("- Filtre de marché : appliqué à la courbe (le portefeuille continue de vivre pendant "
      "les phases en bons du Trésor) ; rotation approximative.")
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


# ----------------------------------------------------------------------------
# Programme principal
# ----------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    C.ensure_dirs()
    settings, protocol, concepts = C.settings(), C.protocol(), C.concepts()
    vetoes = C.vetoes()
    data = PL.collect(settings, concepts, offline=True)
    info, current, history = data["info"], data["current"], data["history"]
    states = PL.build_states(info, concepts)
    prices = P.load_prices()
    dropped = PL.drop_reused_tickers(info, prices, history)
    earn = {float(c): SEC.earnings_dates(int(c)) for c in info["cik"].dropna().unique()}
    ctx = FT.Context(prices=prices, states=states, info=info, history=history, current=current,
                     excluded_sectors=settings["universe"]["excluded_sectors"], earnings=earn,
                     market=settings["backtest"]["benchmarks"]["equal_weight"])
    cal = ctx.calendar
    today = cal[-1]
    log.info("Données jusqu'au %s, %d symboles réattribués écartés", today.date(), len(dropped))

    # Calendriers : site, décalé d'un mois (test de robustesse du protocole), tranches
    pf = settings["portfolio"]
    if pf.get("holding", "band") != "band":
        raise RuntimeError("Cette analyse suppose la règle « band » du site")
    shifted = protocol.get("robustness", {}).get("review_shift_1m", {}).get(
        "review_months", [((m % 12) + 1) for m in pf["review_months"]])
    schedules = {"site": list(pf["review_months"]), "decale": list(shifted)}
    bt_start = pd.Timestamp(settings["backtest"]["start"])
    day = pf["review_day"]
    official = sorted(set(PL.month_ends(cal, bt_start)) |
                      set(review_dates(cal[:-1], sorted(set(pf["review_months"]) |
                                                      set(shifted)), day, bt_start)))
    month_ends = sorted(PL.month_ends(cal, bt_start))
    all_mid = review_dates(cal[:-1], list(range(1, 13)), day, bt_start)
    dates = sorted(set(month_ends) | set(all_mid))
    log.info("Classements à %d dates (fins de mois et mi-mois)", len(dates))
    panel = PL.build_panel(ctx, dates, settings, vetoes)

    min_elig = settings["backtest"]["min_eligible"]
    valid_start = next((d for d in official if int(panel[d]["eligible_base"].sum()) >= min_elig),
                       None)
    if valid_start is None:
        raise RuntimeError("Jamais assez de titres éligibles")
    adj = prices["adj_close"].ffill()
    bench = {k: adj[v] for k, v in settings["backtest"]["benchmarks"].items() if v in adj}
    rf_sym = settings["backtest"]["risk_free"]
    rf_daily = (prices["close"][rf_sym].ffill() / 100 / 252) if rf_sym in prices["close"] \
        else pd.Series(0.0, index=cal)
    mk = Market(adj, rf_daily, settings["backtest"]["benchmarks"]["equal_weight"],
                settings["backtest"]["benchmarks"]["sp500"])
    min_f = settings["scoring"]["min_factors"]
    start = str(valid_start.date())
    hold_start = protocol["holdout"]["start"]
    (a1, b1), (a2, b2) = protocol["subperiods"]
    periods = {"totale": (start, None), "2011-2015": (max(a1, start), b1),
               "2016-2020": (a2, b2), "reservee": (hold_start, None)}
    month_end_pos = [cal.get_loc(d) for d in PL.month_ends(cal, cal[0])]
    me_in_panel = [d for d in month_ends if d in panel]
    models = list(protocol["models"])
    hold = pf["hold_rank"]
    labels = {v: r.label.format(h=hold, h15=int(hold * 1.5), h2=int(hold * 2), h3=int(hold * 3))
              for v, r in VARIANTES.items()}

    rows, curves, verification, per_sale, per_review = [], {}, {}, [], []
    calendars: dict[str, dict] = {}
    full: dict = {}
    for model in models:
        t1 = time.time()
        base = C.portfolio_params(settings, protocol["variants"]["reference"], model)
        ranks = {d: B.rank_frame(panel[d], base, min_f) for d in dates if d >= bt_start}
        revs = {s: [r for r in review_dates(cal[:-1], months, day, valid_start) if r in panel]
                for s, months in schedules.items()}
        sleeve_revs = [[r for r in review_dates(cal[:-1], months, day, valid_start) if r in panel]
                       for months in SLEEVES]

        # Vérification : la règle du site reproduit backtest.run
        for s, rv in revs.items():
            params = {**base, "review_months": schedules[s]}
            ref = B.run(f"{model}:{s}", panel, adj, params, rv, min_f)
            sim = simulate(f"{model}:{s}:reference", mk, ranks, params, rv,
                           VARIANTES["reference"], me_in_panel)
            a, b = sim.equity.align(ref.equity, join="outer")
            mism = 0
            for x in sim.review_log:
                held_now = {t: 0 for t in x["keep"] + list(x["reasons"])}
                held_rule = review_decision(ranks[x["decision"]], held_now, params, 0)
                if set(held_rule.keep) != set(x["keep"]) or set(held_rule.buy) != set(x["buy"]):
                    mism += 1
            verification[f"{model} {s}"] = (
                f"écart relatif max {float((a / b - 1).abs().max()):.1e}, "
                f"{len(sim.positions)} ventes contre {len(ref.positions)}, "
                f"décisions différentes de review_decision : {mism}")
            log.info("%s %s : %s", model, s, verification[f"{model} {s}"])

        for v, rules in VARIANTES.items():
            for s, rv in revs.items():
                key = f"{model}:{s}:{v}"
                params = {**base, "review_months": schedules[s]}
                try:
                    if rules.overlay:
                        res = simulate(key, mk, ranks, params, rv, VARIANTES["reference"],
                                       me_in_panel)
                        res = with_overlay(res, mk, params, month_end_pos)
                    else:
                        res = simulate(key, mk, ranks, params, rv, rules, me_in_panel)
                except Exception:  # noqa: BLE001
                    log.error("%s : échec\n%s", key, traceback.format_exc())
                    continue
                met = all_metrics(res, bench, rf_daily, periods)
                full[key] = met
                for p, m in met.items():
                    rows.append({"variante": v, "modele": model, "calendrier": s, "periode": p,
                                 **{k: m.get(k) for k in (
                                     "cagr", "volatility", "sharpe", "max_drawdown",
                                     "excess_equal_weight", "excess_sp500", "ir_equal_weight",
                                     "turnover_per_year", "positions_closed", "hit_rate",
                                     "ventes_par_an", "duree_mediane_jours", "frais_par_an",
                                     "stops_par_an", "poids_max_moyen",
                                     "poids_max_avant_revue", "part_detenue_12m_plus")}})
                if s == "site":
                    curves[f"{model}:{v}"] = B.weekly(res.equity / res.equity.iloc[0])
                    if v in ("reference", "combinaison"):
                        a_, b_ = sale_diagnostics(res, mk, ranks, params,
                                                  {"modele": model, "variante": v})
                        per_sale += a_
                        per_review += b_
                log.info("  %-20s %-7s CAGR totale %s", v, s,
                         pct((met.get("totale") or {}).get("cagr"), 2, False))

        # Tranches et chance du calendrier (même fenêtre pour tous)
        for v in TRANCHE_VARIANTS:
            rules = VARIANTES[v]
            try:
                comb, sleeves = run_tranches(f"{model}:tranches:{v}", mk, ranks, base,
                                             sleeve_revs, rules, me_in_panel)
            except Exception:  # noqa: BLE001
                log.error("tranches %s %s : échec\n%s", model, v, traceback.format_exc())
                continue
            common = comb.all_invested
            win = {"totale": (str(common.date()), None),
                   "2011-2015": (str(common.date()), periods["2011-2015"][1]),
                   "2016-2020": periods["2016-2020"], "reservee": periods["reservee"]}
            met = all_metrics(comb, bench, rf_daily, win)
            full[f"{model}:tranches:{v}"] = met
            for p, m in met.items():
                rows.append({"variante": f"tranches_{v}", "modele": model,
                             "calendrier": "3 tranches", "periode": p, **{k: m.get(k) for k in (
                                 "cagr", "volatility", "sharpe", "max_drawdown",
                                 "excess_equal_weight", "excess_sp500", "ir_equal_weight",
                                 "turnover_per_year", "positions_closed", "hit_rate",
                                 "ventes_par_an", "duree_mediane_jours", "frais_par_an")}})
            curves[f"{model}:tranches_{v}"] = B.weekly(comb.equity / comb.equity.iloc[0])
            if v == "reference":
                ctx_rows = {}
                for s, rv in revs.items():
                    params = {**base, "review_months": schedules[s]}
                    res = simulate("x", mk, ranks, params, rv, rules, me_in_panel)
                    ctx_rows[f"site {schedules[s]}" if s == "site" else f"décalé {schedules[s]}"] = \
                        B.metrics(res, bench, rf_daily, str(common.date()), None).get("cagr")
                for k, sl in enumerate(sleeves):
                    ctx_rows[f"tranche seule {SLEEVES[k]}"] = \
                        B.metrics(sl, bench, rf_daily, str(common.date()), None).get("cagr")
                ctx_rows["3 tranches (règle du site)"] = met["totale"].get("cagr")
                for name, val in ctx_rows.items():
                    calendars.setdefault(name, {})[model] = val
            else:
                calendars.setdefault("3 tranches + combinaison", {})[model] = \
                    met["totale"].get("cagr")
            calendars["_start"] = {"date": str(common.date())}
        log.info("%s terminé en %.0fs", model, time.time() - t1)

    table = pd.DataFrame(rows)
    table.to_csv(OUT / "tableau.csv", index=False)
    vd = verdicts(table, models, list(schedules))
    sales = summarize_sales([x for x in per_sale if x["variante"] == "reference"],
                            [x for x in per_review if x["variante"] == "reference"], hold)
    sales_comb = summarize_sales([x for x in per_sale if x["variante"] == "combinaison"],
                                 [x for x in per_review if x["variante"] == "combinaison"], hold)
    pd.DataFrame(per_sale).to_csv(OUT / "diagnostic_ventes.csv", index=False)
    pd.DataFrame(per_review).to_csv(OUT / "diagnostic_revues.csv", index=False)
    common_start = calendars.pop("_start", {}).get("date")
    pd.DataFrame(calendars).T.to_csv(OUT / "calendriers.csv", index_label="calendrier")
    pd.DataFrame(curves).sort_index().to_csv(OUT / "courbes.csv", index_label="date")
    meta = {
        "genere_le": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "donnees_jusquau": today, "debut": valid_start, "periodes": periods,
        "calendriers": schedules, "tranches": SLEEVES, "frais": pf["cost_per_trade"],
        "variantes": {v: {"libelle": labels[v], **{k: getattr(r, k) for k in (
            "family", "hold_mult", "min_hold_days", "hard_exit_mult", "smooth", "weighting",
            "band", "stop", "stop_level", "overlay")}} for v, r in VARIANTES.items()},
        "verdicts": vd, "ventes_reference": sales, "ventes_combinaison": sales_comb,
        "calendriers_cagr": calendars, "mesures": full,
    }
    (OUT / "comparaison.json").write_text(json.dumps(R.clean(meta), ensure_ascii=False, indent=1),
                                          encoding="utf-8")
    verification["durée (s)"] = round(time.time() - t0)
    (OUT / "verification.json").write_text(json.dumps(R.clean(verification), ensure_ascii=False,
                                                      indent=1), encoding="utf-8")
    write_summary(OUT / "resume.md", {
        "data_end": today.date(), "start": valid_start.date(), "cost": pf["cost_per_trade"],
        "hold": hold, "n": pf["n_positions"], "verification": verification, "sales": sales,
        "verdicts": vd, "labels": labels, "models": models, "schedules": list(schedules),
        "table": table, "calendars": calendars, "common_start": common_start})
    log.info("Terminé en %.0fs", time.time() - t0)


if __name__ == "__main__":
    main()
