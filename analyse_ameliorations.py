"""Analyse ponctuelle (branche temporaire) : corrections proposées pour V1, V2 et V3.

Question : les corrections proposées le 22/10/2026 améliorent-elles les trois modèles, et
lequel des modèles corrigés donne les meilleurs résultats ? Deux volets :

1. Chaque correction (« levier ») appliquée seule à chaque modèle, comparée à sa référence.
2. Quatre modèles corrigés définis d'avance (V1+, V2+, V3+ et V4, la fusion), comparés entre
   eux, à leur référence et aux indices.

Protocole, rédigé le 04/11/2026 AVANT toute exécution sur les données réelles
-----------------------------------------------------------------------------
Toute la période 2011-2026 a déjà été vue (période réservée révélée le 17/10/2026) : aucun
résultat de cette analyse ne vaut validation. Pour limiter le risque de retenir un hasard :

1. Mesure sans la chance du calendrier. Chaque stratégie est jouée en 3 tranches d'un tiers,
   revues à des mois décalés (janvier-avril-juillet-octobre, février-mai-août-novembre,
   mars-juin-septembre-décembre, le 15 ou la séance suivante) et mesurée à partir du jour où
   les trois tranches sont investies. Le calendrier du site n'est donné qu'à titre
   d'information.
2. Liste fermée (LEVIERS et CORRIGES ci-dessous) : rien n'est ajouté, retiré ni réglé après
   lecture des résultats. Quand un facteur perd du poids, ce poids est redistribué au prorata
   des autres facteurs du modèle, sauf mention contraire. Pour être classé, un titre doit
   avoir 4 facteurs du modèle (règle du site) ; dans un modèle à 4 facteurs, 3 suffisent, pour
   tolérer comme ailleurs un facteur manquant.
3. Chaque levier est appliqué seul à chaque modèle concerné. Cellules : modèles concernés x
   2 périodes (2011-2020 et depuis 2021).
4. Levier de rendement « candidat » si son rendement annualisé net de frais bat celui de la
   référence dans au moins 5 cellules sur 6 (dans toutes s'il y en a moins de 6), si l'écart
   moyen sur la période totale est positif et si la perte maximale moyenne ne se dégrade pas
   de plus de 3 points.
5. Levier de risque « candidat » si le ratio de Sharpe progresse dans au moins 5 cellules sur
   6, si la volatilité moyenne ou la perte maximale moyenne s'améliore sur la période totale
   et si le rendement moyen ne baisse pas de plus de 0,5 point par an.
6. Le contrôle des données n'est pas jugé sur la performance : il corrige des erreurs et
   figure dans tous les modèles corrigés. Son effet seul est donné à titre d'information.
7. Modèles corrigés jugés sur la période totale, en tranches. L'un d'eux n'est déclaré
   meilleur que si son avance de rendement sur chacun des trois autres dépasse deux erreurs
   types (t >= 2 sur l'écart de rendement quotidien). Sinon : pas de gagnant net, et le choix
   se fait sur le profil recherché (rendement ou risque), pas sur le rang dans le backtest.
8. Rien n'est adopté sur le site sans 12 mois de suivi en parallèle.

Mêmes conventions que le backtest du site : décision à la clôture du jour de revue, ordres à
la clôture suivante, 0,10 % de frais par transaction, dividendes réinvestis, mêmes limites
(sociétés sans cours absentes, pas de filtre d'offre de rachat dans l'historique). La
référence jouée au calendrier du site doit reproduire backtest.run à l'identique.

Leviers (chacun seul)
---------------------
- vol_secteur     : volatilité sur 12 mois classée au sein du secteur, et non plus sur tout
                    l'univers (comme la qualité et la valorisation).
- sans_risque     : facteur risque retiré du score.
- mom_residuel    : momentum résiduel (Blitz, Huij et Martens, 2011) à la place du momentum
                    brut : rendement propre au titre sur 12-1 et 6-1 mois, hors exposition au
                    S&P 500 estimée sur 3 ans de séances (au moins 1 an), divisé par sa
                    volatilité.
- rachats_10      : facteur « rachats nets » à 10 % (autres poids x 0,9) : variation sur un an
                    du nombre d'actions, corrigée des fractionnements, classée au sein du
                    secteur ; moins d'actions = mieux (Pontiff et Woodgate, 2008).
- sans_croissance : V1 seulement : facteur croissance retiré.
- resultats_10    : V2 et V3 : facteur résultats ramené de 20 % à 10 %.
- duree_6m        : pas de vente sur le rang avant 6 mois de détention, sauf rang > 150.
- plafond_3       : 3 lignes au plus par secteur (au lieu de 5).
- poids_vol       : poids inversement proportionnels à la volatilité sur 12 mois, bornés entre
                    la moitié et le double du poids égal.
- lignes_30       : 30 lignes, conservation jusqu'au rang 75, 7 lignes au plus par secteur.
- donnees         : contrôle du nombre d'actions. Rotation quotidienne moyenne inférieure à
                    0,02 % ou supérieure à 50 % de la capitalisation, ou nombre d'actions
                    multiplié ou divisé par plus de 4 par rapport aux deux années précédentes :
                    la capitalisation, donc la valorisation, est tenue pour inconnue.

Modèles corrigés
----------------
Communs : 20 lignes, conservation jusqu'au rang 50, 3 lignes au plus par secteur, 6 mois
minimum (sauf rang > 150), données contrôlées.
- V1+ : rachats 25 % (à la place de la croissance), momentum 25 %, qualité 20 %,
        valorisation 15 %, risque classé au sein du secteur 15 %. Poids égaux.
- V2+ : momentum résiduel 39,375 %, qualité 28,125 %, valorisation 11,25 %, risque classé au
        sein du secteur 11,25 %, résultats 10 %. Poids égaux.
- V3+ : momentum 34,6 %, qualité 34,6 %, valorisation 20,8 %, résultats 10 % (facteur risque
        retiré du score) ; poids inversement proportionnels à la volatilité. 20 lignes pour
        rester comparable aux autres : l'effet de 30 lignes est mesuré par lignes_30.
- V4  : fusion : momentum résiduel, qualité, valorisation, rachats et résultats à 20 % chacun,
        toutes les mesures classées au sein du secteur ; facteur risque retiré ; poids
        inversement proportionnels à la volatilité.

Sorties dans resultats/ : resume.md, tableau.csv, leviers.csv, comparaisons.csv,
facteurs.csv, secteurs.csv, courbes.csv, donnees.json, verification.json, comparaison.json.
"""
from __future__ import annotations

import json
import logging
import math
import os
import sys
import time
import traceback
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from screener import backtest as B  # noqa: E402
from screener import config as C  # noqa: E402
from screener import features as FT  # noqa: E402
from screener import fundamentals as FD  # noqa: E402
from screener import ic as IC  # noqa: E402
from screener import pipeline as PL  # noqa: E402
from screener import prices as P  # noqa: E402
from screener import report as R  # noqa: E402
from screener import scoring as S  # noqa: E402
from screener import sec as SEC  # noqa: E402
from screener.portfolio import review_dates, review_decision  # noqa: E402

log = logging.getLogger("analyse")
OUT = Path(os.environ.get("ANALYSE_OUT", "resultats"))
MODELS = ("v1", "v2", "v3")
SLEEVES = ([1, 4, 7, 10], [2, 5, 8, 11], [3, 6, 9, 12])
MIN_HOLD_DAYS = 175          # « 6 mois » : protégé à la revue suivante, vendable à la deuxième
HARD_EXIT_MULT = 3.0         # ... sauf rang > 3 x le seuil de conservation
INVVOL_BOUNDS = (0.5, 2.0)   # en multiples du poids égal
MDD_TOLERANCE = 0.03
CAGR_TOLERANCE_RISK = 0.005
T_BEST = 2.0
DAYS_3Y = 756
CELL_PERIODS = ("conception", "reservee")
DEBUG_TICKERS = ("XOM", "WAT", "FERG")
NEW_FACTORS = ["risk_sec", "mom_res", "mom_res_sec", "earnings_sec", "buyback", "value_chk"]
FACTOR_NAMES = {
    "growth": "Croissance", "earnings": "Résultats", "momentum": "Momentum",
    "quality": "Qualité", "value": "Valorisation", "risk": "Risque",
    "risk_sec": "Risque (au sein du secteur)", "mom_res": "Momentum résiduel",
    "mom_res_sec": "Momentum résiduel (au sein du secteur)",
    "earnings_sec": "Résultats (au sein du secteur)", "buyback": "Rachats nets",
    "value_chk": "Valorisation (données contrôlées)",
}


# ----------------------------------------------------------------------------
# Pondérations
# ----------------------------------------------------------------------------

def site_weights(settings: dict, model: str) -> dict:
    """Pondérations du site, dans l'ordre de config.FACTORS (même ordre de sommation que
    scoring.composite, pour reproduire les scores à l'identique)."""
    return {f: w for f, w in C.model_weights(settings, model).items() if w > 0}


def prorata(w: dict, fixed: dict) -> dict:
    """Fixe certains poids (0 = facteur retiré) ; les autres sont rééchelonnés au prorata pour
    que le total reste 100 %."""
    out = {c: v for c, v in w.items() if c not in fixed}
    total_fixed = sum(fixed.values())
    s = sum(out.values())
    out = {c: v * (1.0 - total_fixed) / s for c, v in out.items()}
    for c, v in fixed.items():
        if v > 0:
            out[c] = v
    order = [c for c in w if c in out] + [c for c in out if c not in w]
    return {c: out[c] for c in order}


def rename(w: dict, mapping: dict) -> dict:
    return {mapping.get(c, c): v for c, v in w.items()}


@dataclass(frozen=True)
class Strategy:
    key: str
    model: str                 # modèle de départ (v1, v2, v3) ; « v4 » pour la fusion
    label: str
    family: str                # reference, rendement, risque, correction, corrige
    weights: tuple             # ((colonne, poids), ...)
    n_positions: int = 20
    hold_rank: int = 50
    max_sector: int = 5
    min_hold_days: int = 0
    weighting: str = "equal"   # equal ou invvol

    @property
    def w(self) -> dict:
        return dict(self.weights)


LEVIERS: dict[str, dict] = {
    "vol_secteur": dict(family="rendement", label="Volatilité classée au sein du secteur",
                        w=lambda w: rename(w, {"risk": "risk_sec"})),
    "sans_risque": dict(family="rendement", label="Facteur risque retiré du score",
                        w=lambda w: prorata(w, {"risk": 0.0})),
    "mom_residuel": dict(family="rendement", label="Momentum résiduel à la place du momentum brut",
                         w=lambda w: rename(w, {"momentum": "mom_res"})),
    "rachats_10": dict(family="rendement", label="Rachats nets à 10 % (autres poids x 0,9)",
                       w=lambda w: prorata(w, {"buyback": 0.10})),
    "sans_croissance": dict(family="rendement", label="Facteur croissance retiré (V1)",
                            models=("v1",), w=lambda w: prorata(w, {"growth": 0.0})),
    "resultats_10": dict(family="rendement", label="Résultats ramenés de 20 % à 10 % (V2, V3)",
                         models=("v2", "v3"), w=lambda w: prorata(w, {"earnings": 0.10})),
    "duree_6m": dict(family="rendement",
                     label="6 mois minimum avant une vente sur le rang (sauf rang > 150)",
                     rules=dict(min_hold_days=MIN_HOLD_DAYS)),
    "plafond_3": dict(family="risque", label="3 lignes au plus par secteur",
                      rules=dict(max_sector=3)),
    "poids_vol": dict(family="risque",
                      label="Poids inversement proportionnels à la volatilité (bornés)",
                      rules=dict(weighting="invvol")),
    "lignes_30": dict(family="risque", label="30 lignes, conservation jusqu'au rang 75",
                      rules=dict(n_positions=30, hold_rank=75, max_sector=7)),
    "donnees": dict(family="correction", label="Contrôle du nombre d'actions",
                    w=lambda w: rename(w, {"value": "value_chk"})),
}

COMMON_FIX = dict(max_sector=3, min_hold_days=MIN_HOLD_DAYS)
CORRIGES: dict[str, dict] = {
    "v1+": dict(model="v1", label="V1 corrigée",
                w=lambda sw: rename(sw["v1"], {"growth": "buyback", "value": "value_chk",
                                               "risk": "risk_sec"}),
                rules=dict(COMMON_FIX)),
    "v2+": dict(model="v2", label="V2 corrigée",
                w=lambda sw: rename(prorata(sw["v2"], {"earnings": 0.10}),
                                    {"momentum": "mom_res", "value": "value_chk",
                                     "risk": "risk_sec"}),
                rules=dict(COMMON_FIX)),
    "v3+": dict(model="v3", label="V3 corrigée",
                w=lambda sw: rename(prorata(sw["v3"], {"earnings": 0.10, "risk": 0.0}),
                                    {"value": "value_chk"}),
                rules=dict(COMMON_FIX, weighting="invvol")),
    "v4": dict(model="v4", label="V4 fusion",
               w=lambda sw: {"earnings_sec": 0.2, "mom_res_sec": 0.2, "quality": 0.2,
                             "value_chk": 0.2, "buyback": 0.2},
               rules=dict(COMMON_FIX, weighting="invvol")),
}


def build_strategies(settings: dict) -> dict[tuple[str, str], Strategy]:
    sw = {m: site_weights(settings, m) for m in MODELS}
    out = {}
    for m in MODELS:
        out[(m, "reference")] = Strategy("reference", m, "Règles du site", "reference",
                                         tuple(sw[m].items()))
        for key, spec in LEVIERS.items():
            if spec.get("models") and m not in spec["models"]:
                continue
            w = spec["w"](sw[m]) if "w" in spec else sw[m]
            out[(m, key)] = Strategy(key, m, spec["label"], spec["family"], tuple(w.items()),
                                     **spec.get("rules", {}))
    for key, spec in CORRIGES.items():
        w = spec["w"](sw)
        out[(spec["model"], key)] = Strategy(key, spec["model"], spec["label"], "corrige",
                                             tuple(w.items()), **spec["rules"])
    for s in out.values():
        if abs(sum(s.w.values()) - 1.0) > 1e-9:
            raise ValueError(f"{s.model}:{s.key} : pondérations de somme {sum(s.w.values())}")
    return out


# ----------------------------------------------------------------------------
# Nouvelles mesures
# ----------------------------------------------------------------------------

class Extras:
    """Momentum résiduel, rachats nets et contrôle du nombre d'actions, à une date donnée,
    avec les seules données disponibles ce jour-là."""

    def __init__(self, ctx: FT.Context, settings: dict):
        adj = ctx.prices["adj_close"]
        self.L = ctx.logret.to_numpy(dtype=float)
        self.col = {t: j for j, t in enumerate(adj.columns)}
        self.m = self.col.get(settings["backtest"]["benchmarks"]["sp500"])
        self.splits = {}
        for t, g in ctx.split_lookup.items():
            g = g.sort_values("date")
            d = g["date"].to_numpy().astype("datetime64[D]").astype(np.int64)
            r = g["ratio"].to_numpy(dtype=float)
            self.splits[t] = (d, np.cumprod(r[::-1])[::-1])
        self.sh = {}
        st = ctx.states
        for cik, g in st.groupby("cik", sort=False):
            g = g.sort_values("usable_date", kind="mergesort")
            u = g["usable_date"].to_numpy().astype("datetime64[D]").astype(np.int64)
            sd_raw = pd.to_datetime(g["shares_date"]).to_numpy().astype("datetime64[D]")
            sd = np.where(np.isnat(sd_raw), np.int64(-10 ** 9),
                          sd_raw.astype(np.int64))
            sh = pd.to_numeric(g["shares"], errors="coerce").to_numpy(dtype=float)
            dil = g["flags"].fillna("").astype(str).str.contains(
                "moyenne diluée", regex=False).to_numpy()
            self.sh[float(cik)] = (u, sh, sd, dil)

    # -- fractionnements -------------------------------------------------------------
    def sf(self, t: str, day: np.ndarray | int) -> np.ndarray:
        """Produit des fractionnements postérieurs au jour `day` (entiers, jours depuis 1970),
        comme Context.split_factor ; vectorisé."""
        day = np.atleast_1d(np.asarray(day, dtype=np.int64))
        s = self.splits.get(t)
        if s is None:
            return np.ones(len(day))
        d, suf = s
        k = np.searchsorted(d, day, side="right")
        out = np.ones(len(day))
        ok = k < len(d)
        out[ok] = suf[k[ok]]
        return out

    # -- momentum résiduel ---------------------------------------------------------------
    def residual_momentum(self, p: int, tickers: list[str]) -> tuple[np.ndarray, np.ndarray]:
        n_t = len(tickers)
        r12, r6 = np.full(n_t, np.nan), np.full(n_t, np.nan)
        pos = [(i, self.col[t]) for i, t in enumerate(tickers) if t in self.col]
        if self.m is None or p < 252 or not pos:
            return r12, r6
        rows, idx = zip(*pos)
        lo = max(1, p - (DAYS_3Y - 1))
        Y = self.L[lo:p + 1][:, list(idx)]
        X = self.L[lo:p + 1, self.m]
        V = np.isfinite(Y) & np.isfinite(X)[:, None]
        n = V.sum(axis=0).astype(float)
        with np.errstate(invalid="ignore", divide="ignore"):
            Xb = np.where(V, X[:, None], 0.0)
            Yb = np.where(V, Y, 0.0)
            mx, my = Xb.sum(0) / n, Yb.sum(0) / n
            dx = np.where(V, X[:, None] - mx, 0.0)
            dy = np.where(V, Y - my, 0.0)
            beta = (dx * dy).sum(0) / (dx * dx).sum(0)
            alpha = my - beta * mx
            E = np.where(V, Y - alpha - beta * X[:, None], np.nan)

            def window(a: int, b: int) -> np.ndarray:
                W = E[a - lo:b - lo + 1]
                cnt = np.isfinite(W).sum(0)
                s = np.nansum(W, axis=0)
                sd = np.nanstd(W, axis=0, ddof=1)
                z = s / (sd * np.sqrt(cnt))
                bad = (cnt < 0.8 * (b - a + 1)) | (n < 252) | ~np.isfinite(z)
                return np.where(bad, np.nan, z)

            z12 = window(p - 251, p - 21)
            z6 = window(p - 125, p - 21)
        r12[list(rows)] = z12
        r6[list(rows)] = z6
        return r12, r6

    # -- rachats nets ------------------------------------------------------------------
    def _latest(self, cik: float, day: int):
        rec = self.sh.get(cik)
        if rec is None:
            return None, -1
        u = rec[0]
        k = int(np.searchsorted(u, day, side="right")) - 1
        return rec, k

    def net_issuance(self, t: str, cik: float, day: int) -> float:
        rec, k = self._latest(cik, day)
        if rec is None or k < 0:
            return np.nan
        _, sh, sd, dil = rec
        if not (np.isfinite(sh[k]) and sh[k] > 0) or sd[k] < 0 or day - sd[k] > 200:
            return np.nan
        target = sd[k] - 365
        gap = np.abs(sd[:k + 1] - target)
        ok = (sd[:k + 1] >= 0) & np.isfinite(sh[:k + 1]) & (sh[:k + 1] > 0) & \
            (dil[:k + 1] == dil[k]) & (gap <= 45)
        if not ok.any():
            return np.nan
        cand = np.nonzero(ok)[0]
        best = gap[cand].min()
        j = int(cand[gap[cand] == best][-1])
        f = self.sf(t, np.array([sd[k], sd[j]]))
        ratio = sh[k] * f[0] / (sh[j] * f[1])
        if not (0.5 <= ratio <= 3.0):
            return np.nan
        return float(math.log(ratio))

    # -- contrôle du nombre d'actions ----------------------------------------------------
    def suspect(self, t: str, cik: float, day: int, mcap: float, dvol: float) -> bool:
        if np.isfinite(mcap) and mcap > 0 and np.isfinite(dvol) and dvol > 0:
            turn = dvol / mcap
            if turn < 2e-4 or turn > 0.5:
                return True
        rec, k = self._latest(cik, day)
        if rec is None or k < 0:
            return False
        u, sh, sd, _ = rec
        if not (np.isfinite(sh[k]) and sh[k] > 0) or sd[k] < 0:
            return False
        h = np.nonzero((u <= day - 90) & (u >= day - 730) & np.isfinite(sh) & (sh > 0) &
                       (sd >= 0))[0]
        if len(h) < 2:
            return False
        now = sh[k] * self.sf(t, sd[k])[0]
        past = float(np.median(sh[h] * self.sf(t, sd[h])))
        ratio = now / past if past > 0 else np.nan
        return bool(np.isfinite(ratio) and (ratio > 4.0 or ratio < 0.25))


# ----------------------------------------------------------------------------
# Classements
# ----------------------------------------------------------------------------

def factor_mean(parts: list[pd.Series], need: int) -> pd.Series:
    df = pd.concat(parts, axis=1)
    return df.mean(axis=1).where(df.notna().sum(axis=1) >= need)


def panel_frame(ctx: FT.Context, when: pd.Timestamp, settings: dict, vetoes: list,
                ex: Extras) -> pd.DataFrame:
    """Comme pipeline.panel_frame, plus les nouvelles mesures et les nouveaux facteurs."""
    feats = FT.compute(ctx, when, live=False)
    p = ctx.pos(when)
    day = int(np.datetime64(ctx.calendar[p].date(), "D").astype(np.int64))
    tick = list(feats.index)
    r12, r6 = ex.residual_momentum(p, tick)
    feats["res_12_1"] = r12
    feats["res_6_1"] = r6
    ciks = pd.to_numeric(feats["cik"], errors="coerce").to_numpy(dtype=float)
    mcap = pd.to_numeric(feats.get("market_cap"), errors="coerce").to_numpy(dtype=float) \
        if "market_cap" in feats else np.full(len(tick), np.nan)
    dvol = pd.to_numeric(feats.get("dollar_vol_63"), errors="coerce").to_numpy(dtype=float) \
        if "dollar_vol_63" in feats else np.full(len(tick), np.nan)
    ni, sus = np.full(len(tick), np.nan), np.zeros(len(tick), dtype=bool)
    for i, t in enumerate(tick):
        if not np.isfinite(ciks[i]):
            continue
        ni[i] = ex.net_issuance(t, float(ciks[i]), day)
        sus[i] = ex.suspect(t, float(ciks[i]), day, mcap[i], dvol[i])
    feats["net_iss"] = ni
    feats["suspect"] = sus

    scored = S.score(feats, settings)
    filt = S.apply_filters(scored, settings, vetoes=PL.vetoes_at(vetoes, when))
    comps = [f"composite_{m}" for m in settings["models"]]
    out = filt[["sector", *C.FACTORS, *comps, "above_sma200"]].copy()
    out["scorable"] = scored["reasons"].map(len) == 0
    out["eligible_base"] = filt["eligible_base"]

    mss = settings["scoring"]["min_sector_size"]
    scorable = out["scorable"]
    sectors = scored["sector"].fillna("Inconnu")

    def pct(series: pd.Series, higher: bool, by_sector: bool) -> pd.Series:
        v = pd.to_numeric(series, errors="coerce").where(scorable).astype(float)
        v = v.replace([np.inf, -np.inf], np.nan)
        return S.ranked(v, sectors, higher, by_sector, mss)

    bad = scored["suspect"].astype(bool)
    out["risk_sec"] = pct(scored["vol_12m"], False, True)
    out["mom_res"] = factor_mean([pct(scored["res_12_1"], True, False),
                                  pct(scored["res_6_1"], True, False)], 1)
    out["mom_res_sec"] = factor_mean([pct(scored["res_12_1"], True, True),
                                      pct(scored["res_6_1"], True, True)], 1)
    out["earnings_sec"] = factor_mean([pct(scored["sue"], True, True),
                                       pct(scored["ear"], True, True),
                                       scored["pct_gp_change"]], 2)
    out["buyback"] = pct(scored["net_iss"], False, True)
    out["value_chk"] = factor_mean([pct(scored["fcf_yield"].where(~bad), True, True),
                                    pct(scored["ebit_ev"].where(~bad), True, True)], 1)
    for c in ("vol_12m", "mom_12_1", "res_12_1", "res_6_1", "net_iss", "suspect"):
        out[c] = scored[c]
    return out


def factors_needed(n_active: int, min_factors: int) -> int:
    """Facteurs exigés pour être classé. Modèles à 5 facteurs ou plus : comme le site
    (min_factors, soit 4). Modèles à 4 facteurs ou moins : un facteur manquant toléré, comme
    pour les modèles à 5 facteurs du site (le site en exigerait 4 sur 4, ce qui réduirait
    l'univers et fausserait la comparaison)."""
    return min_factors if n_active > min_factors else max(n_active - 1, 1)


def composite_cols(df: pd.DataFrame, weights: dict, min_factors: int) -> pd.Series:
    """scoring.composite généralisé à n'importe quelles colonnes de facteurs."""
    w = pd.Series(weights, dtype=float)
    active = list(w.index)
    scores = df[active]
    avail = scores.notna()
    wsum = (avail * w[active]).sum(axis=1)
    total = (scores.fillna(0) * w[active]).sum(axis=1) / wsum.where(wsum > 0)
    return total.where(avail.sum(axis=1) >= factors_needed(len(active), min_factors))


def rank_frame(df: pd.DataFrame, weights: dict, min_factors: int) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    out["sector"] = df["sector"]
    out["composite"] = composite_cols(df, weights, min_factors)
    elig = df["eligible_base"].astype(bool) & out["composite"].notna()
    out["eligible"] = elig
    out["rank"] = out["composite"].where(elig).rank(ascending=False, method="first")
    out["vol_12m"] = df["vol_12m"]
    return out


# ----------------------------------------------------------------------------
# Simulation (moteur de l'analyse des sorties, réduit et étendu aux poids par la volatilité)
# ----------------------------------------------------------------------------

class Market:
    def __init__(self, adj: pd.DataFrame, rf_daily: pd.Series, ew: str, sp: str):
        self.cal = adj.index
        self.cols = {t: j for j, t in enumerate(adj.columns)}
        self.px = adj.values
        ratio = np.ones_like(self.px)
        with np.errstate(invalid="ignore", divide="ignore"):
            ratio[1:] = self.px[1:] / self.px[:-1]
        self.ratio = np.where(np.isfinite(ratio), ratio, 1.0)
        self.rf = rf_daily.reindex(self.cal).ffill().fillna(0.0).to_numpy(dtype=float)
        self.ew = self.px[:, self.cols[ew]] if ew in self.cols else None
        self.sp = self.px[:, self.cols[sp]] if sp in self.cols else None
        self.ew_s = pd.Series(self.ew, index=self.cal) if self.ew is not None else None
        self.sp_s = pd.Series(self.sp, index=self.cal) if self.sp is not None else None


def decide(scores: pd.DataFrame, meta: dict, s: Strategy, when: pd.Timestamp):
    """Comme portfolio.review_decision (règle « band »), avec la durée minimale et le plafond
    sectoriel de la stratégie."""
    eligible = scores[scores["eligible"]].sort_values("rank")
    keep, reasons = [], {}
    for t, m in meta.items():
        if t not in eligible.index:
            reasons[t] = "n'est plus éligible"
            continue
        rank = eligible.at[t, "rank"]
        young = s.min_hold_days and (when - m["entry_date"]).days < s.min_hold_days
        hard = rank > s.hold_rank * HARD_EXIT_MULT
        if (young and not hard) or rank <= s.hold_rank:
            keep.append(t)
        else:
            reasons[t] = f"rang {int(rank)}"
    count: dict[str, int] = {}
    for t in keep:
        sec = eligible.at[t, "sector"]
        count[sec] = count.get(sec, 0) + 1
    buy = []
    for t, row in eligible.iterrows():
        if len(keep) + len(buy) >= s.n_positions:
            break
        if t in keep:
            continue
        sec = row["sector"]
        if count.get(sec, 0) >= s.max_sector:
            continue
        buy.append(t)
        count[sec] = count.get(sec, 0) + 1
    return keep, buy, reasons


def bounded_weights(raw: np.ndarray, lo: float, hi: float) -> np.ndarray:
    """w = clip(lambda x raw, lo, hi) avec somme 1 (lambda par dichotomie)."""
    a, b = 0.0, hi / raw.min()
    for _ in range(200):
        mid = (a + b) / 2
        if np.clip(mid * raw, lo, hi).sum() < 1.0:
            a = mid
        else:
            b = mid
    w = np.clip(b * raw, lo, hi)
    return w / w.sum()


def invvol_weights(target: list[str], scores: pd.DataFrame) -> dict:
    vol = pd.to_numeric(scores["vol_12m"].reindex(target), errors="coerce").astype(float)
    med = vol.median()
    vol = vol.fillna(med if np.isfinite(med) else 0.30).clip(lower=0.05)
    n = len(target)
    w = bounded_weights(1.0 / vol.to_numpy(), INVVOL_BOUNDS[0] / n, INVVOL_BOUNDS[1] / n)
    return dict(zip(target, w))


def new_meta(mk: Market, t: str, i: int, ridx: int, scores: pd.DataFrame) -> dict:
    return {"bought_review": ridx, "entry_pos": i, "entry_date": mk.cal[i],
            "sector": scores.at[t, "sector"] if t in scores.index else None}


def closed(mk: Market, t: str, m: dict, i: int, reason: str) -> dict:
    """Même calcul que backtest._closed, plus l'écart à l'équipondéré sur la même période."""
    j = mk.cols[t]
    p0, p1 = mk.px[m["entry_pos"], j], mk.px[i, j]
    ok = bool(p0) and np.isfinite(p0) and np.isfinite(p1)
    rel = None
    if ok and mk.ew is not None:
        rel = float((p1 / p0) / (mk.ew[i] / mk.ew[m["entry_pos"]]) - 1)
    return {"ticker": t, "entry": mk.cal[m["entry_pos"]], "exit": mk.cal[i],
            "return": float(p1 / p0 - 1) if ok else None, "rel_ew": rel, "reason": reason,
            "sector": m["sector"]}


def simulate(name: str, mk: Market, ranks: dict, s: Strategy, cost_rate: float,
             reviews: list) -> B.Result:
    """Simulation quotidienne. Avec les règles du site, reproduit backtest.run à l'identique."""
    cal, cols, ratio = mk.cal, mk.cols, mk.ratio
    review_pos = {cal.get_loc(r): r for r in reviews if r in ranks}
    if not review_pos:
        raise ValueError("Aucune date de revue avec des classements")
    first = min(review_pos)
    values: dict[str, float] = {}
    meta: dict[str, dict] = {}
    cash = 1.0
    eq = np.full(len(cal), np.nan)
    res = B.Result(name=name, params={}, equity=pd.Series(dtype=float))
    res.costs, res.sector_log, res.review_log = [], [], []
    pending = None
    review_idx = -1
    for i in range(first, len(cal)):
        if i > first:
            for t in values:
                values[t] *= ratio[i, cols[t]]
        if pending is not None and pending[0] == i:
            _, keep, buy, reasons, rdate, ridx, scores = pending
            target = keep + buy
            pre = cash + sum(values.values())
            total = pre
            if s.weighting == "equal":
                weights = None
                tgt_val = total / len(target) if target else 0.0
                traded = sum(abs(tgt_val - values.get(t, 0.0)) for t in target)
                traded += sum(v for t, v in values.items() if t not in target)
                cost = traded * cost_rate
                total -= cost
                tgt_val = total / len(target) if target else 0.0
            else:
                weights = invvol_weights(target, scores) if target else {}
                traded = sum(abs(weights[t] * total - values.get(t, 0.0)) for t in target)
                traded += sum(v for t, v in values.items() if t not in target)
                cost = traded * cost_rate
                total -= cost
            sold = []
            for t in list(values):
                if t not in target:
                    m = meta.pop(t)
                    res.positions.append(closed(mk, t, m, i, reasons.get(t, "")))
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
            res.reviews.append({"review_date": rdate, "executed": cal[i], "buy": list(buy),
                                "sell": sold, "holdings": list(target), "cost": cost})
            res.review_log.append({"decision": rdate, "keep": list(keep), "buy": list(buy),
                                   "sell": sold, "reasons": list(reasons)})
            res.sector_log.append((cal[i], {t: (meta[t]["sector"], values[t] / post)
                                            for t in target} if post > 0 else {}))
            pending = None
        eq[i] = cash + sum(values.values())
        if i + 1 >= len(cal):
            continue
        if i in review_pos:
            review_idx += 1
            rdate = review_pos[i]
            scores = ranks[rdate]
            keep, buy, reasons = decide(scores, meta, s, rdate)
            pending = (i + 1, keep, buy, reasons, rdate, review_idx, scores)
    res.equity = pd.Series(eq, index=cal).dropna()
    last = len(cal) - 1
    for t, m in meta.items():
        res.holdings[t] = {"entry_date": m["entry_date"], "sector": m["sector"],
                           "weight": values[t] / eq[last] if eq[last] else None}
    return res


def run_tranches(name: str, mk: Market, ranks: dict, s: Strategy, cost_rate: float,
                 sleeve_reviews: list) -> B.Result:
    """Trois portefeuilles d'un tiers chacun, revus à des mois décalés. Avant sa première
    revue, une tranche attend en bons du Trésor (comme dans l'analyse des sorties)."""
    sleeves = [simulate(f"{name}:t{k + 1}", mk, ranks, s, cost_rate, revs)
               for k, revs in enumerate(sleeve_reviews)]
    cal = mk.cal
    i0 = min(cal.get_loc(x.equity.index[0]) for x in sleeves)
    idx = cal[i0:]
    parts = []
    for x in sleeves:
        i_s = cal.get_loc(x.equity.index[0])
        growth = np.cumprod(np.r_[1.0, 1.0 + mk.rf[i0 + 1:i_s + 1]])
        v = np.empty(len(idx))
        v[:i_s - i0 + 1] = growth / 3.0
        e = x.equity.to_numpy()
        v[i_s - i0:] = growth[-1] / 3.0 * e / e[0]
        parts.append(pd.Series(v, index=idx))
    total = sum(parts)
    out = B.Result(name=name, params={}, equity=total)
    share = [p / total for p in parts]
    out.turnover = [(d, x * float(sh.asof(d))) for sl, sh in zip(sleeves, share)
                    for d, x in sl.turnover]
    out.costs = [(d, c * float(sh.asof(d))) for sl, sh in zip(sleeves, share)
                 for d, c in sl.costs]
    out.positions = [p for sl in sleeves for p in sl.positions]
    out.reviews = [rv for sl in sleeves for rv in sl.reviews]
    out.sector_log = [x for sl in sleeves for x in sl.sector_log]
    out.holdings = {f"t{k + 1}": sl.holdings for k, sl in enumerate(sleeves)}
    out.all_invested = max(x.equity.index[0] for x in sleeves)
    out.sleeves = sleeves
    return out


# ----------------------------------------------------------------------------
# Mesures
# ----------------------------------------------------------------------------

def measure(res: B.Result, mk: Market, bench: dict, rf_daily: pd.Series, start, end) -> dict:
    a = max(pd.Timestamp(start), res.equity.index[0])
    m = B.metrics(res, bench, rf_daily, str(a.date()), end)
    if not m:
        return {}
    b = pd.Timestamp(end) if end else res.equity.index[-1]
    e = res.equity.loc[a:b]
    years = (e.index[-1] - e.index[0]).days / 365.25
    r = e.pct_change().dropna()
    if mk.sp_s is not None:
        rs = mk.sp_s.reindex(e.index).pct_change().reindex(r.index)
        m["beta_sp"] = float(r.cov(rs) / rs.var()) if rs.var() > 0 else None
    for key, ser in (("sp", mk.sp_s), ("ew", mk.ew_s)):
        if ser is None:
            continue
        bs = ser.reindex(e.index)
        rel = ((e / e.shift(DAYS_3Y)) / (bs / bs.shift(DAYS_3Y))).dropna()
        m[f"part_3ans_{key}"] = float((rel > 1).mean()) if len(rel) else None
    cl = [p for p in res.positions if a <= p["exit"] <= b]
    rel = [p["rel_ew"] for p in cl if p.get("rel_ew") is not None]
    days = [(p["exit"] - p["entry"]).days for p in cl]
    m["lignes_bat_ew"] = float(np.mean([x > 0 for x in rel])) if rel else None
    m["ventes_par_an"] = len(cl) / years if years > 0 else None
    m["duree_mediane_jours"] = float(np.median(days)) if days else None
    costs = sum(c for d, c in getattr(res, "costs", []) if a <= d <= b)
    m["frais_par_an"] = costs / years if years > 0 else None
    return m


def tstat(e1: pd.Series, e2: pd.Series, start, end) -> tuple[float | None, float | None]:
    a, b = pd.Timestamp(start), (pd.Timestamp(end) if end else None)
    x, y = e1.loc[a:b], e2.loc[a:b]
    x, y = x.align(y, join="inner")
    d = (x.pct_change() - y.pct_change()).dropna()
    if len(d) < 60 or d.std() == 0:
        return None, None
    return float(d.mean() * 252), float(d.mean() / d.std() * math.sqrt(len(d)))


def sector_exposure(res: B.Result, start) -> dict:
    """Poids moyen par secteur aux revues (toutes tranches), à partir de `start`."""
    acc: dict[str, float] = {}
    n = 0
    for d, hold in res.sector_log:
        if d < pd.Timestamp(start) or not hold:
            continue
        n += 1
        for sec, w in hold.values():
            acc[sec or "Inconnu"] = acc.get(sec or "Inconnu", 0.0) + w
    return {k: v / n for k, v in sorted(acc.items())} if n else {}


def success(panel_me: dict, adj: pd.DataFrame, col: str, end_limit: pd.Timestamp,
            h: int = 12, top_n: int = 20) -> dict:
    """Comme ic.success_rates, pour une colonne de score quelconque."""
    cal = adj.index
    rows = []
    for d in sorted(panel_me):
        df = panel_me[d]
        if col not in df:
            continue
        comp = df[col].where(df["eligible_base"].astype(bool)).dropna()
        tick = [t for t in comp.index if t in adj.columns]
        fwd = d + pd.DateOffset(months=h)
        if len(tick) < 5 * top_n or fwd > end_limit:
            continue
        p0 = cal.searchsorted(d, side="right") - 1
        p1 = cal.searchsorted(fwd, side="right") - 1
        ret = (adj.iloc[p1][tick] / adj.iloc[p0][tick] - 1).dropna()
        if len(ret) < 5 * top_n:
            continue
        sc = comp.loc[ret.index]
        mean = ret.mean()
        order = sc.sort_values(ascending=False).index
        top = ret.loc[order[:top_n]]
        q = pd.qcut(sc.rank(method="first", ascending=False), 5, labels=False)
        rows.append({"base_rate": float((ret > mean).mean()),
                     "top_rate": float((top > mean).mean()),
                     "top_excess": float(top.mean() - mean),
                     "spread": float(ret[q == 0].mean() - ret[q == 4].mean())})
    if not rows:
        return {}
    o = pd.DataFrame(rows)
    n = len(o)
    sd = o["spread"].std()
    return {"n_mois": n, "taux_de_base": float(o["base_rate"].mean()),
            "taux_top20": float(o["top_rate"].mean()),
            "ecart_top20": float(o["top_excess"].mean()),
            "ecart_q1_q5": float(o["spread"].mean()),
            "t_q1_q5": float(o["spread"].mean() / sd * math.sqrt(max(n / h, 1)))
            if sd > 0 else None}


# ----------------------------------------------------------------------------
# Diagnostics des données
# ----------------------------------------------------------------------------

def diag_company(ctx: FT.Context, concepts: dict, ticker: str, today: pd.Timestamp) -> dict:
    out: dict = {"ticker": ticker}
    if ticker not in ctx.info.index:
        out["erreur"] = "absent de la table des titres"
        return out
    cik = ctx.info.at[ticker, "cik"]
    out["cik"] = None if pd.isna(cik) else int(cik)
    if pd.isna(cik):
        return out
    facts = SEC.load_facts(int(cik))
    if facts is None or facts.empty:
        out["faits"] = "aucun fait XBRL en cache"
        return out
    g = facts.groupby(["concept", "tag", "unit"]).agg(
        n=("val", "size"), dernier_fin=("end", "max"), dernier_depot=("filed", "max"),
        formulaires=("form", lambda s: ",".join(sorted(set(map(str, s))))))
    out["faits"] = [{**dict(zip(["concept", "tag", "unit"], k)), **{
        kk: (str(vv.date()) if isinstance(vv, pd.Timestamp) else vv) for kk, vv in v.items()}}
        for k, v in g.to_dict("index").items()]
    st = ctx.states[ctx.states["cik"] == float(cik)]
    out["etats"] = int(len(st))
    out["derniers_etats"] = [{k: (str(v) if not isinstance(v, (int, float)) else v)
                              for k, v in r.items()} for r in st.tail(3).to_dict("records")]
    try:
        comp = FD.Company(facts, concepts)
        out["versions"] = len(comp.versions)
        out["concepts_12m"] = sorted(comp.ttm)
        out["concepts_trimestres"] = sorted(comp.quarters)
        stt = comp.state(np.datetime64(today.date(), "D"))
        out["etat_du_jour"] = {k: (str(v) if not isinstance(v, (int, float)) or
                                   (isinstance(v, float) and not math.isfinite(v)) else v)
                               for k, v in stt.items()}
        for concept in ("revenue", "net_income", "assets", "operating_income"):
            q = dict(comp.quarters.get(concept) or [])
            ttm = dict(comp.ttm.get(concept) or [])
            out[f"{concept}_series"] = {
                "trimestres": {tg: [str(np.datetime64(x, "D")) for x in ser.end[-6:]]
                               for tg, ser in q.items()},
                "douze_mois": {tg: [str(np.datetime64(x, "D")) for x in ser.end[-4:]]
                               for tg, ser in ttm.items()}}
    except Exception:  # noqa: BLE001
        out["exception"] = traceback.format_exc()[-3000:]
    return out


# ----------------------------------------------------------------------------
# Rapport lisible
# ----------------------------------------------------------------------------

def pct(x, digits=1, plus=True):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "–"
    return R.fr(100 * x, digits, plus) + " %"


def num(x, digits=1, plus=False):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "–"
    return R.fr(x, digits, plus)


def wtext(w: dict) -> str:
    return ", ".join(f"{FACTOR_NAMES.get(c, c)} {R.fr(100 * v, 1, False)} %"
                     for c, v in sorted(w.items(), key=lambda x: -x[1]))


def write_summary(path: Path, c: dict) -> None:
    L: list[str] = []
    a = L.append
    a("# Analyse ponctuelle des corrections de V1, V2 et V3\n")
    a(f"Données jusqu'au {c['data_end']}. Mesure en 3 tranches à partir du {c['common']} "
      f"(les trois tranches investies). Frais : {pct(c['cost'], 2, False)} par transaction.\n")
    a("Protocole fixé le 04/11/2026 avant exécution (en-tête d'analyse_ameliorations.py). "
      "Toute la période a déjà été vue : ces résultats sont des indices, pas des preuves.\n")
    a("## 1. Vérification\n")
    for k, v in c["verification"].items():
        a(f"- {k} : {v}")
    a("")
    a("## 2. Leviers seuls : écart à la référence (en tranches)\n")
    a("Écarts de rendement annualisé net de frais en points (moyenne des modèles concernés). "
      "Perte maximale et volatilité : un écart positif est une amélioration. t : écart de "
      "rendement quotidien rapporté à son erreur type, période totale, moyenne des modèles.\n")
    a("| Levier | Famille | Cellules gagnantes | Totale | 2011-2020 | 2021+ | t | Perte max | "
      "Volatilité | Sharpe | Écart de suivi S&P | Verdict |")
    a("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in c["levers"]:
        a(f"| {r['levier']} | {r['famille']} | {r['cellules_gagnantes']}/{r['cellules']} | "
          f"{pct(r['ecart_cagr_totale'], 2)} | {pct(r['ecart_cagr_conception'], 2)} | "
          f"{pct(r['ecart_cagr_reservee'], 2)} | {num(r['t_moyen'], 1, True)} | "
          f"{pct(r['ecart_perte_max'])} | {pct(r['ecart_volatilite'])} | "
          f"{num(r['ecart_sharpe'], 2, True)} | {pct(r['ecart_te_sp'])} | {r['verdict']} |")
    a("")
    a("Détail par modèle, période totale (écart de rendement annualisé, t) :\n")
    a("| Levier | " + " | ".join(m.upper() for m in MODELS) + " |")
    a("|---|" + "---|" * len(MODELS))
    for r in c["levers"]:
        cells = []
        for m in MODELS:
            x = r["par_modele"].get(m)
            cells.append("–" if not x else f"{pct(x['ecart'], 2)} (t {num(x['t'], 1, True)})")
        a(f"| {r['levier']} | " + " | ".join(cells) + " |")
    a("")
    a("## 3. Modèles corrigés (en tranches)\n")
    a("| Stratégie | Rendement/an | Volatilité | Sharpe | Perte max | Bêta | Écart S&P | "
      "Écart équipondéré | Écart de suivi S&P | 3 ans battant le S&P | Lignes battant "
      "l'équipondéré | Ventes/an |")
    a("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in c["models_table"]:
        x = r["totale"]
        a(f"| {r['nom']} | {pct(x.get('cagr'), 1, False)} | {pct(x.get('volatility'), 1, False)} | "
          f"{num(x.get('sharpe'), 2)} | {pct(x.get('max_drawdown'))} | {num(x.get('beta_sp'), 2)} | "
          f"{pct(x.get('excess_sp500'))} | {pct(x.get('excess_equal_weight'))} | "
          f"{pct(x.get('te_sp500'), 1, False)} | {pct(x.get('part_3ans_sp'), 0, False)} | "
          f"{pct(x.get('lignes_bat_ew'), 0, False)} | {num(x.get('ventes_par_an'), 0)} |")
    a("")
    a("Par période (rendement annualisé) :\n")
    a("| Stratégie | 2011-2015 | 2016-2020 | 2011-2020 | 2021+ |")
    a("|---|---|---|---|---|")
    for r in c["models_table"]:
        a(f"| {r['nom']} | {pct((r.get('2011-2015') or {}).get('cagr'), 1, False)} | "
          f"{pct((r.get('2016-2020') or {}).get('cagr'), 1, False)} | "
          f"{pct((r.get('conception') or {}).get('cagr'), 1, False)} | "
          f"{pct((r.get('reservee') or {}).get('cagr'), 1, False)} |")
    a("")
    a("Comparaisons (période totale ; écart de rendement annualisé moyen, t) :\n")
    a("| Comparaison | Écart | t |")
    a("|---|---|---|")
    for r in c["pairs"]:
        a(f"| {r['a']} − {r['b']} | {pct(r['ecart'], 2)} | {num(r['t'], 1, True)} |")
    a("")
    a(f"**Verdict (règle 7) :** {c['best']}\n")
    a("Pondérations :\n")
    for k, w in c["weights"].items():
        a(f"- {k} : {wtext(w)}")
    a("")
    a("## 4. Pouvoir prédictif (corrélation de rang avec le rendement futur)\n")
    a("| Score ou facteur | IC 6 mois | t | IC 12 mois | t | Top 20 battant l'univers à 12 mois "
      "(taux de base) | Q1 − Q5 à 12 mois |")
    a("|---|---|---|---|---|---|---|")
    for r in c["ic_rows"]:
        a(f"| {r['nom']} | {num(r.get('ic6'), 3, True)} | {num(r.get('t6'), 1, True)} | "
          f"{num(r.get('ic12'), 3, True)} | {num(r.get('t12'), 1, True)} | "
          f"{pct(r.get('top'), 1, False)} ({pct(r.get('base'), 1, False)}) | "
          f"{pct(r.get('spread'), 1)} |")
    a("")
    a("## 5. Exposition sectorielle moyenne (poids aux revues)\n")
    secs = c["sector_cols"]
    a("| Stratégie | " + " | ".join(secs) + " |")
    a("|---|" + "---|" * len(secs))
    for name, row in c["sectors"].items():
        a(f"| {name} | " + " | ".join(pct(row.get(s), 0, False) for s in secs) + " |")
    a("")
    a("## 6. Données\n")
    for k, v in c["data_notes"].items():
        a(f"- {k} : {v}")
    a("")
    a("## Limites\n")
    a("- Période entière déjà vue : ces écarts sont des indices, pas des preuves ; plusieurs "
      "leviers testés à la fois rendent probable qu'un d'eux paraisse bon par hasard.")
    a("- Sociétés sans cours Yahoo absentes (biais de survivance, voir l'onglet Données).")
    a("- Rachats nets : nombre d'actions de la page de garde des rapports (ou moyenne diluée), "
      "comparé à celui d'il y a un an de même source ; les erreurs de données passent en partie.")
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


# ----------------------------------------------------------------------------
# Programme principal
# ----------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    warnings.filterwarnings("ignore", category=RuntimeWarning)
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
    verification: dict = {}
    data_notes: dict = {}

    pf = settings["portfolio"]
    if pf.get("holding", "band") != "band" or pf.get("trend_filter"):
        raise RuntimeError("Cette analyse suppose la règle « band » du site, sans filtre")
    day = pf["review_day"]
    bt_start = pd.Timestamp(settings["backtest"]["start"])
    shifted = protocol.get("robustness", {}).get("review_shift_1m", {}).get(
        "review_months", [((m % 12) + 1) for m in pf["review_months"]])
    official = sorted(set(PL.month_ends(cal, bt_start)) |
                      set(review_dates(cal[:-1], sorted(set(pf["review_months"]) | set(shifted)),
                                       day, bt_start)))
    month_ends = sorted(PL.month_ends(cal, bt_start))
    all_mid = review_dates(cal[:-1], list(range(1, 13)), day, bt_start)
    dates = sorted(set(month_ends) | set(all_mid))
    ex = Extras(ctx, settings)
    log.info("Classements à %d dates (fins de mois et mi-mois)", len(dates))
    panel = {}
    t1 = time.time()
    for k, d in enumerate(dates):
        panel[d] = panel_frame(ctx, d, settings, vetoes, ex)
        if k % 50 == 0:
            log.info("Classements : %d/%d (%s), %.0fs", k + 1, len(dates), d.date(),
                     time.time() - t1)
    log.info("Classements calculés en %.0fs", time.time() - t1)

    # Contrôle : colonnes du site identiques à pipeline.panel_frame
    base_cols = ["sector", *C.FACTORS, *[f"composite_{m}" for m in settings["models"]],
                 "scorable", "eligible_base"]
    worst, bad_dates = 0.0, 0
    for d in (dates[0], dates[len(dates) // 2], dates[-1]):
        ref = PL.panel_frame(ctx, d, settings, vetoes)
        mine = panel[d]
        for col in base_cols:
            x, y = ref[col], mine[col].reindex(ref.index)
            if col in ("sector",):
                same = (x.fillna("") == y.fillna("")).all()
                bad_dates += 0 if same else 1
            elif x.dtype == bool or col in ("scorable", "eligible_base"):
                bad_dates += 0 if (x.astype(bool) == y.astype(bool)).all() else 1
            else:
                xv, yv = x.astype(float).to_numpy(), y.astype(float).to_numpy()
                both = np.isnan(xv) & np.isnan(yv)
                diff = np.where(both, 0.0, np.abs(xv - yv))
                worst = max(worst, float(np.nanmax(diff)) if len(diff) else 0.0)
                bad_dates += int(np.isnan(diff).any())
    verification["Classements du site reproduits (3 dates)"] = (
        f"écart max {worst:.1e}, colonnes différentes : {bad_dates}")
    log.info("Contrôle des classements : %s", verification["Classements du site reproduits (3 dates)"])

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
    cost = pf["cost_per_trade"]
    strategies = build_strategies(settings)
    mid_dates = [d for d in all_mid if d in panel and d >= valid_start]
    site_revs = [r for r in review_dates(cal[:-1], pf["review_months"], day, valid_start)
                 if r in panel]
    sleeve_revs = [[r for r in review_dates(cal[:-1], months, day, valid_start) if r in panel]
                   for months in SLEEVES]

    rank_cache: dict = {}

    def ranks_for(s: Strategy) -> dict:
        key = s.weights
        if key not in rank_cache:
            rank_cache[key] = {d: rank_frame(panel[d], s.w, min_f) for d in mid_dates}
        return rank_cache[key]

    # Vérification : la référence au calendrier du site reproduit backtest.run
    for m in MODELS:
        s = strategies[(m, "reference")]
        params = C.portfolio_params(settings, protocol["variants"]["reference"], m)
        ref = B.run(f"{m}:site", panel, adj, params, site_revs, min_f)
        rk = ranks_for(s)
        sim = simulate(f"{m}:site:reference", mk, rk, s, cost, site_revs)
        x, y = sim.equity.align(ref.equity, join="outer")
        mism = 0
        for rv in sim.review_log:
            held_now = {t: 0 for t in rv["keep"] + rv["reasons"]}
            rule = review_decision(rk[rv["decision"]], held_now, params, 0)
            if set(rule.keep) != set(rv["keep"]) or set(rule.buy) != set(rv["buy"]):
                mism += 1
        same_rank = all(
            (B.rank_frame(panel[d], params, min_f)["rank"].fillna(-1) ==
             rk[d]["rank"].fillna(-1)).all() for d in site_revs)
        verification[f"{m.upper()} au calendrier du site"] = (
            f"écart relatif max {float((x / y - 1).abs().max()):.1e}, {len(sim.positions)} "
            f"ventes contre {len(ref.positions)}, décisions différentes de review_decision : "
            f"{mism}, rangs identiques à backtest.rank_frame : {'oui' if same_rank else 'non'}")
        log.info("%s : %s", m, verification[f"{m.upper()} au calendrier du site"])

    # Toutes les stratégies : 3 tranches (+ calendrier du site, pour information)
    results: dict = {}
    site_results: dict = {}
    t2 = time.time()
    for (m, key), s in strategies.items():
        try:
            rk = ranks_for(s)
            results[(m, key)] = run_tranches(f"{m}:{key}", mk, rk, s, cost, sleeve_revs)
            site_results[(m, key)] = simulate(f"{m}:{key}:site", mk, rk, s, cost, site_revs)
        except Exception:  # noqa: BLE001
            log.error("%s %s : échec\n%s", m, key, traceback.format_exc())
    log.info("%d stratégies simulées en %.0fs", len(results), time.time() - t2)
    common = max(r.all_invested for r in results.values())
    periods = {"totale": (common, None), "conception": (common, "2020-12-31"),
               "reservee": (pd.Timestamp(protocol["holdout"]["start"]), None),
               "2011-2015": (common, "2015-12-31"), "2016-2020": ("2016-01-01", "2020-12-31")}

    def name_of(m: str, key: str) -> str:
        if key == "reference":
            return f"{m.upper()} (référence)"
        if key in CORRIGES:
            return CORRIGES[key]["label"].replace("V1 corrigée", "V1+").replace(
                "V2 corrigée", "V2+").replace("V3 corrigée", "V3+")
        return f"{m.upper()} {key}"

    rows, full = [], {}
    for (m, key), res in results.items():
        met = {p: measure(res, mk, bench, rf_daily, a, b) for p, (a, b) in periods.items()}
        full[f"{m}:{key}"] = met
        for p, x in met.items():
            rows.append({"strategie": key, "modele": m, "calendrier": "tranches", "periode": p,
                         **{k: x.get(k) for k in (
                             "cagr", "volatility", "sharpe", "max_drawdown", "beta_sp",
                             "excess_sp500", "excess_equal_weight", "te_sp500", "ir_sp500",
                             "part_3ans_sp", "part_3ans_ew", "lignes_bat_ew", "hit_rate",
                             "turnover_per_year", "ventes_par_an", "duree_mediane_jours",
                             "frais_par_an")}})
    for (m, key), res in site_results.items():
        x = measure(res, mk, bench, rf_daily, valid_start, None)
        rows.append({"strategie": key, "modele": m, "calendrier": "site", "periode": "totale",
                     **{k: x.get(k) for k in ("cagr", "volatility", "sharpe", "max_drawdown",
                                              "excess_sp500", "excess_equal_weight")}})
    table = pd.DataFrame(rows)
    table.to_csv(OUT / "tableau.csv", index=False)

    def get(m, key, p, col):
        x = (full.get(f"{m}:{key}") or {}).get(p) or {}
        v = x.get(col)
        return None if v is None or (isinstance(v, float) and not np.isfinite(v)) else float(v)

    def mean_diff(key, ms, p, col="cagr", sign=1.0):
        d = []
        for m in ms:
            a, b = get(m, key, p, col), get(m, "reference", p, col)
            if a is not None and b is not None:
                d.append(sign * (a - b))
        return float(np.mean(d)) if d else None

    # Leviers : verdicts (règles 4 à 6)
    lever_rows = []
    tvals: dict = {}
    for key, spec in LEVIERS.items():
        ms = [m for m in MODELS if (m, key) in results and (m, "reference") in results]
        cells, sh_cells, per = [], [], {}
        for m in ms:
            for p in CELL_PERIODS:
                a, b = get(m, key, p, "cagr"), get(m, "reference", p, "cagr")
                if a is not None and b is not None:
                    cells.append(a - b)
                a, b = get(m, key, p, "sharpe"), get(m, "reference", p, "sharpe")
                if a is not None and b is not None:
                    sh_cells.append(a - b)
            a, b = get(m, key, "totale", "cagr"), get(m, "reference", "totale", "cagr")
            mean_d, t = tstat(results[(m, key)].equity, results[(m, "reference")].equity,
                              common, None)
            tvals[(m, key)] = t
            per[m] = {"ecart": (a - b) if a is not None and b is not None else None, "t": t,
                      "ecart_quotidien_annualise": mean_d}
        if not cells:
            continue
        n_cells = len(cells)
        need = 5 if n_cells == 6 else n_cells
        ts = [tvals[(m, key)] for m in ms if tvals[(m, key)] is not None]
        row = {"levier": key, "libelle": spec["label"], "famille": spec["family"],
               "cellules": n_cells, "cellules_gagnantes": int(sum(x > 0 for x in cells)),
               "cellules_sharpe": int(sum(x > 0 for x in sh_cells)),
               "ecart_cagr_totale": mean_diff(key, ms, "totale"),
               "ecart_cagr_conception": mean_diff(key, ms, "conception"),
               "ecart_cagr_reservee": mean_diff(key, ms, "reservee"),
               "ecart_perte_max": mean_diff(key, ms, "totale", "max_drawdown"),
               "ecart_volatilite": mean_diff(key, ms, "totale", "volatility", -1.0),
               "ecart_te_sp": mean_diff(key, ms, "totale", "te_sp500", -1.0),
               "ecart_sharpe": float(np.mean(sh_cells)) if sh_cells else None,
               "t_moyen": float(np.mean(ts)) if ts else None,
               "par_modele": per}
        if spec["family"] == "correction":
            verdict = "correction (non jugée)"
        elif spec["family"] == "risque":
            ok = row["cellules_sharpe"] >= need and \
                ((row["ecart_volatilite"] or 0) > 0 or (row["ecart_perte_max"] or 0) > 0) and \
                (row["ecart_cagr_totale"] or -1) >= -CAGR_TOLERANCE_RISK
            verdict = "candidat" if ok else "rejeté"
        else:
            ok = row["cellules_gagnantes"] >= need and (row["ecart_cagr_totale"] or -1) > 0 and \
                (row["ecart_perte_max"] or 0) >= -MDD_TOLERANCE
            verdict = "candidat" if ok else "rejeté"
        row["verdict"] = verdict
        lever_rows.append(row)
    pd.DataFrame([{k: v for k, v in r.items() if k != "par_modele"} for r in lever_rows]).to_csv(
        OUT / "leviers.csv", index=False)

    # Modèles corrigés : tableau, comparaisons, verdict (règle 7)
    corr_keys = [(CORRIGES[k]["model"], k) for k in CORRIGES if (CORRIGES[k]["model"], k) in results]
    show = [(m, "reference") for m in MODELS] + corr_keys
    models_table = []
    for m, key in show:
        models_table.append({"nom": name_of(m, key), "modele": m, "strategie": key,
                             **{p: full[f"{m}:{key}"].get(p) or {} for p in periods}})
    for bk, label in (("sp500", "S&P 500"), ("equal_weight", "S&P 500 équipondéré")):
        if bk not in bench:
            continue
        ser = bench[bk].dropna()
        pseudo = B.Result(name=bk, params={}, equity=ser.loc[common:])
        pseudo.costs = []
        models_table.append({"nom": label, "modele": bk, "strategie": "indice",
                             **{p: measure(pseudo, mk, bench, rf_daily, a, b)
                                for p, (a, b) in periods.items()}})
    pairs = []
    for i, (m1, k1) in enumerate(corr_keys):
        for m2, k2 in corr_keys[i + 1:]:
            d, t = tstat(results[(m1, k1)].equity, results[(m2, k2)].equity, common, None)
            pairs.append({"a": name_of(m1, k1), "b": name_of(m2, k2), "ecart": d, "t": t,
                          "ka": k1, "kb": k2})
    for m, key in corr_keys:
        base = CORRIGES[key]["model"]
        for bm in ([base] if base in MODELS else list(MODELS)):
            d, t = tstat(results[(m, key)].equity, results[(bm, "reference")].equity, common, None)
            pairs.append({"a": name_of(m, key), "b": name_of(bm, "reference"), "ecart": d, "t": t,
                          "ka": key, "kb": f"{bm}:reference"})
        for bk, label in (("sp500", "S&P 500"), ("equal_weight", "S&P 500 équipondéré")):
            if bk in bench:
                d, t = tstat(results[(m, key)].equity, bench[bk], common, None)
                pairs.append({"a": name_of(m, key), "b": label, "ecart": d, "t": t, "ka": key,
                              "kb": bk})
    for i, m1 in enumerate(MODELS):
        for m2 in MODELS[i + 1:]:
            d, t = tstat(results[(m1, "reference")].equity, results[(m2, "reference")].equity,
                         common, None)
            pairs.append({"a": name_of(m1, "reference"), "b": name_of(m2, "reference"),
                          "ecart": d, "t": t, "ka": f"{m1}:reference", "kb": f"{m2}:reference"})
    pd.DataFrame(pairs).to_csv(OUT / "comparaisons.csv", index=False)
    best = None
    for m, key in corr_keys:
        ts = []
        for r in pairs:
            if r["ka"] == key and r["kb"] in CORRIGES:
                ts.append(r["t"])
            elif r["kb"] == key and r["ka"] in CORRIGES:
                ts.append(-r["t"] if r["t"] is not None else None)
        if ts and all(t is not None and t >= T_BEST for t in ts):
            best = name_of(m, key)
    by_cagr = sorted(corr_keys, key=lambda k: -(get(k[0], k[1], "totale", "cagr") or -9))
    best_text = (f"{best} : avance de plus de deux erreurs types sur chacun des autres."
                 if best else
                 "pas de gagnant net (aucun modèle corrigé ne devance tous les autres de plus "
                 "de deux erreurs types). Ordre des rendements, pour information : " +
                 ", ".join(f"{name_of(m, k)} {pct(get(m, k, 'totale', 'cagr'), 1, False)}"
                           for m, k in by_cagr) + ".")

    # Pouvoir prédictif des scores et des facteurs (fins de mois)
    me = {d: panel[d] for d in month_ends if d in panel and d >= valid_start}
    comp_cols = {}
    for m in MODELS:
        comp_cols[f"composite_{m}"] = f"Score {m.upper()} (site)"
    for m, key in corr_keys:
        col = f"comp_{key}"
        w = strategies[(m, key)].w
        for d in me:
            me[d] = me[d].assign(**{col: composite_cols(me[d], w, min_f)})
        comp_cols[col] = f"Score {name_of(m, key)}"
    ic_cols = list(comp_cols) + C.FACTORS + NEW_FACTORS
    ic_rows = []
    try:
        obs = IC.ic_observations(me, adj, [6, 12], today, columns=ic_cols)
        summ = IC.summarize(obs) if len(obs) else []
        idx = {(r["factor"], r["horizon"]): r for r in summ}
        for col in ic_cols:
            r6, r12 = idx.get((col, 6), {}), idx.get((col, 12), {})
            row = {"colonne": col, "nom": comp_cols.get(col, FACTOR_NAMES.get(col, col)),
                   "ic6": r6.get("mean_ic"), "t6": r6.get("t_overlap_adj"),
                   "ic12": r12.get("mean_ic"), "t12": r12.get("t_overlap_adj")}
            if col in comp_cols:
                sx = success(me, adj, col, today)
                row.update(top=sx.get("taux_top20"), base=sx.get("taux_de_base"),
                           spread=sx.get("ecart_q1_q5"), t_spread=sx.get("t_q1_q5"))
            ic_rows.append(row)
    except Exception:  # noqa: BLE001
        log.error("Pouvoir prédictif : échec\n%s", traceback.format_exc())
    pd.DataFrame(ic_rows).to_csv(OUT / "facteurs.csv", index=False)

    # Nouvelles mesures : couverture et liens avec les anciennes
    try:
        cov, corr = {}, {}
        for c in ("res_12_1", "net_iss", "risk_sec", "mom_res", "buyback", "value_chk"):
            cov[c] = float(np.mean([me[d][c].where(me[d]["scorable"]).notna().sum() /
                                    max(int(me[d]["scorable"].sum()), 1) for d in me]))
        for a_, b_ in (("mom_res", "momentum"), ("risk_sec", "risk"), ("buyback", "quality"),
                       ("buyback", "value"), ("buyback", "momentum"), ("value_chk", "value"),
                       ("earnings_sec", "earnings"), ("mom_res_sec", "mom_res")):
            corr[f"{a_}~{b_}"] = float(np.nanmean([me[d][[a_, b_]].corr(method="spearman").iloc[0, 1]
                                                   for d in me]))
        iss = np.concatenate([me[d]["net_iss"].where(me[d]["eligible_base"]).dropna().to_numpy()
                              for d in me])
        data_notes["Couverture des nouvelles mesures (part des titres classables)"] = \
            ", ".join(f"{k} {pct(v, 0, False)}" for k, v in cov.items())
        data_notes["Corrélation de rang moyenne avec les anciens facteurs"] = \
            ", ".join(f"{k} {num(v, 2, True)}" for k, v in corr.items())
        data_notes["Rachats nets : variation annuelle médiane du nombre d'actions"] = \
            f"{pct(float(np.expm1(np.median(iss))), 1)} (quartiles {pct(float(np.expm1(np.quantile(iss, 0.25))), 1)} ; " \
            f"{pct(float(np.expm1(np.quantile(iss, 0.75))), 1)})" if len(iss) else "–"
        last = panel[mid_dates[-1]]
        el = last[last["eligible_base"].astype(bool)]
        disp = {c: float(el.groupby("sector")[c].mean().std()) for c in ("risk", "risk_sec")}
        data_notes[f"Dispersion entre secteurs du score de risque ({mid_dates[-1].date()})"] = \
            f"classé sur tout l'univers {num(disp['risk'], 1)} points, au sein du secteur " \
            f"{num(disp['risk_sec'], 1)} points"
    except Exception:  # noqa: BLE001
        log.error("Statistiques des nouvelles mesures : échec\n%s", traceback.format_exc())

    # Contrôle des données
    flagged: dict = {}
    for d in dates:
        df = panel[d]
        for t in df.index[df["suspect"].astype(bool) & df["scorable"].astype(bool)]:
            f = flagged.setdefault(t, {"premiere": d, "derniere": d, "dates": 0})
            f["derniere"] = d
            f["dates"] += 1
    data_notes["Titres au nombre d'actions suspect (au moins une date)"] = \
        f"{len(flagged)} : " + ", ".join(
            f"{t} ({v['premiere'].date()} → {v['derniere'].date()}, {v['dates']} dates)"
            for t, v in sorted(flagged.items(), key=lambda x: -x[1]["dates"])[:30])
    diags = {t: diag_company(ctx, concepts, t, today) for t in DEBUG_TICKERS}
    (OUT / "donnees.json").write_text(json.dumps(R.clean({"suspects": flagged, "societes": diags}),
                                                 ensure_ascii=False, indent=1), encoding="utf-8")
    for t, dg in diags.items():
        st = dg.get("etat_du_jour") or {}
        data_notes[f"{t} (diagnostic)"] = (
            f"{dg.get('etats', 0)} états, concepts 12 mois : {', '.join(dg.get('concepts_12m', [])) or '–'} ; "
            f"CA 12 mois du jour : {st.get('revenue_ttm', '–')}, actions : {st.get('shares', '–')}"
            + (" ; EXCEPTION" if dg.get("exception") else ""))

    # Expositions sectorielles
    sec_rows = {}
    for m, key in show:
        sec_rows[name_of(m, key)] = sector_exposure(results[(m, key)], common)
    all_secs = sorted({s for r in sec_rows.values() for s in r},
                      key=lambda s: -np.mean([r.get(s, 0) for r in sec_rows.values()]))
    pd.DataFrame(sec_rows).T.to_csv(OUT / "secteurs.csv", index_label="strategie")

    # Courbes hebdomadaires
    curves = {}
    for (m, key), res in results.items():
        e = res.equity.loc[common:]
        curves[f"{m}:{key}"] = B.weekly(e / e.iloc[0])
    for bk in bench:
        e = bench[bk].loc[common:].dropna()
        curves[bk] = B.weekly(e / e.iloc[0])
    pd.DataFrame(curves).sort_index().to_csv(OUT / "courbes.csv", index_label="date")

    weights = {name_of(m, k): strategies[(m, k)].w for m, k in show}
    verification["Stratégies simulées"] = f"{len(results)} (en tranches) et {len(site_results)} " \
                                          f"(calendrier du site)"
    verification["Durée (s)"] = round(time.time() - t0)
    meta = {
        "genere_le": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "donnees_jusquau": today, "debut": valid_start, "tranches_investies": common,
        "periodes": {k: [a, b] for k, (a, b) in periods.items()}, "frais": cost,
        "strategies": {f"{m}:{k}": {"label": s.label, "famille": s.family, "poids": s.w,
                                    "lignes": s.n_positions, "conservation": s.hold_rank,
                                    "plafond_secteur": s.max_sector,
                                    "duree_min_jours": s.min_hold_days,
                                    "ponderation": s.weighting}
                       for (m, k), s in strategies.items()},
        "leviers": lever_rows, "modeles": models_table, "comparaisons": pairs,
        "meilleur": best, "verdict": best_text, "pouvoir_predictif": ic_rows,
        "secteurs": sec_rows, "notes_donnees": data_notes, "mesures": full,
        "site": {f"{m}:{k}": measure(r, mk, bench, rf_daily, valid_start, None)
                 for (m, k), r in site_results.items()},
    }
    (OUT / "comparaison.json").write_text(json.dumps(R.clean(meta), ensure_ascii=False, indent=1),
                                          encoding="utf-8")
    (OUT / "verification.json").write_text(json.dumps(R.clean(verification), ensure_ascii=False,
                                                      indent=1), encoding="utf-8")
    write_summary(OUT / "resume.md", {
        "data_end": today.date(), "common": common.date(), "cost": cost,
        "verification": verification, "levers": lever_rows, "models_table": models_table,
        "pairs": pairs, "best": best_text, "weights": weights, "ic_rows": ic_rows,
        "sectors": sec_rows, "sector_cols": all_secs, "data_notes": data_notes})
    log.info("Terminé en %.0fs", time.time() - t0)


if __name__ == "__main__":
    main()
