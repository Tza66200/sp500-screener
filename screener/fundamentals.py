"""Fondamentaux « point-in-time » : uniquement ce qui était publié à chaque date.

Règles :
1. Pour chaque période déclarée, on garde la PREMIÈRE valeur publiée (pas les retraitements
   ultérieurs), avec sa date de dépôt.
2. Les trimestres sont lus directement (faits de ~3 mois) ou déduits des cumuls depuis le début
   de l'exercice : T2 = S1 - T1, T3 = 9M - S1, T4 = annuel - 9M (ou annuel - T1 - T2 - T3).
   Un trimestre déduit n'est disponible qu'au dépôt le plus tardif de ses composantes.
3. Les chiffres sur 12 mois glissants additionnent 4 trimestres contigus couvrant ~1 an.
4. Un « état » est calculé à chaque date de dépôt : il n'utilise que des données déposées
   au plus tard ce jour-là. Il devient utilisable à la séance SUIVANTE.
"""
from __future__ import annotations

import logging
import math
from bisect import bisect_left

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

Q_RANGE = (75, 120)
Y_RANGE = (340, 390)
TTM_SPAN = (340, 390)
YEAR_TOL = 25          # tolérance (jours) pour retrouver la même période un an plus tôt
STALE_TTM_DAYS = 200   # au-delà, un chiffre 12 mois glissants est jugé périmé
NON_ADDITIVE = {"diluted_shares"}
NON_NEGATIVE = {"revenue", "cost_of_revenue", "capex", "dna", "interest_expense", "gross_profit"}
RESTATE_TOL = 0.005    # écart relatif au-delà duquel une valeur est considérée republiée


# ----------------------------------------------------------------------------
# Construction des séries par étiquette
# ----------------------------------------------------------------------------

def first_filed(df: pd.DataFrame) -> pd.DataFrame:
    """Première valeur publiée pour chaque (étiquette, début, fin)."""
    keys = ["tag", "start", "end"] if "start" in df.columns else ["tag", "end"]
    d = df.sort_values(["filed", "accn"], kind="mergesort")
    return d.drop_duplicates(subset=keys, keep="first")


def _days(start: pd.Timestamp, end: pd.Timestamp) -> int:
    return int((end - start).days) + 1


_EPOCH = np.datetime64("1970-01-01", "D")


def _to_days(s: pd.Series) -> list[int]:
    return list(((s.values.astype("datetime64[D]") - _EPOCH).astype(np.int64)))


def _from_days(x: list[int]) -> pd.Series:
    return pd.to_datetime(np.array(x, dtype=np.int64) * 86400, unit="s")


def build_quarters(f: pd.DataFrame, additive: bool = True, nonneg: bool = False) -> pd.DataFrame:
    """Trimestres d'une étiquette de flux : colonnes start, end, val, avail, derived.

    Calcul en entiers (jours) pour la rapidité ; une ligne = un fait XBRL déjà dédoublonné.
    """
    cols = ["start", "end", "val", "avail", "derived"]
    f = f.dropna(subset=["start"])
    if f.empty:
        return pd.DataFrame(columns=cols)
    S, E, F = _to_days(f["start"]), _to_days(f["end"]), _to_days(f["filed"])
    V = [float(v) for v in f["val"].values]
    facts = sorted(zip(S, E, V, F))
    rows: list[tuple] = []          # (start, end, val, avail, derived)
    annuals = []
    by_start: dict[int, list] = {}
    for s, e, v, fd in facts:
        d = e - s + 1
        if Q_RANGE[0] <= d <= Q_RANGE[1]:
            rows.append((s, e, v, fd, False))
        if additive:
            by_start.setdefault(s, []).append((e, v, fd))
            if Y_RANGE[0] <= d <= Y_RANGE[1]:
                annuals.append((s, e, v, fd))
    if additive:
        for s, items in by_start.items():
            items.sort()
            for (e0, v0, f0), (e1, v1, f1) in zip(items, items[1:]):
                if Q_RANGE[0] <= e1 - e0 <= Q_RANGE[1]:
                    rows.append((e0 + 1, e1, v1 - v0, max(f0, f1), True))
    q = _dedupe(rows)

    # T4 = annuel - (T1 + T2 + T3) quand aucun cumul 9 mois n'est disponible
    ends = {r[1] for r in q}
    extra = []
    for s, e, v, fd in annuals:
        if e in ends:
            continue
        inside = [r for r in q if r[0] >= s - 5 and r[1] <= e - 60]
        if len(inside) != 3 or abs(inside[0][0] - s) > 5:
            continue
        if any(abs(inside[k][0] - inside[k - 1][1] - 1) > 7 for k in (1, 2)):
            continue
        extra.append((inside[-1][1] + 1, e, v - sum(r[2] for r in inside),
                      max([fd] + [r[3] for r in inside]), True))
    if extra:
        q = _dedupe(q + extra)
    if nonneg:
        # Un trimestre reconstitué négatif pour une grandeur toujours positive (chiffre
        # d'affaires, investissements…) trahit des composantes publiées sur des bases
        # différentes (activité cédée, changement de norme) : on l'écarte.
        q = [r for r in q if not (r[4] and r[2] < 0)]
    if not q:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame({
        "start": _from_days([r[0] for r in q]), "end": _from_days([r[1] for r in q]),
        "val": [r[2] for r in q], "avail": _from_days([r[3] for r in q]),
        "derived": [r[4] for r in q]})


def _dedupe(rows: list[tuple]) -> list[tuple]:
    """Un trimestre par date de fin : valeur directe prioritaire, puis la plus tôt disponible."""
    best: dict[int, tuple] = {}
    for r in rows:
        cur = best.get(r[1])
        if cur is None or (r[4], r[3]) < (cur[4], cur[3]):
            best[r[1]] = r
    return [best[k] for k in sorted(best)]


def build_ttm(q: pd.DataFrame) -> pd.DataFrame:
    """12 mois glissants : 4 trimestres contigus couvrant 340 à 390 jours."""
    cols = ["start", "end", "val", "avail"]
    if len(q) < 4:
        return pd.DataFrame(columns=cols)
    q = q.sort_values("end")
    S, E, A = _to_days(q["start"]), _to_days(q["end"]), _to_days(q["avail"])
    V = [float(v) for v in q["val"].values]
    rows = []
    for i in range(len(E)):
        chain = [i]
        cur = i
        for _ in range(3):
            target = S[cur] - 1
            k = bisect_left(E, target - 7)
            j = None
            while k < cur and E[k] <= target + 7:
                if j is None or abs(E[k] - target) < abs(E[j] - target):
                    j = k
                k += 1
            if j is None:
                break
            chain.append(j)
            cur = j
        if len(chain) != 4:
            continue
        span = E[i] - S[chain[-1]] + 1
        if not (TTM_SPAN[0] <= span <= TTM_SPAN[1]):
            continue
        rows.append((S[chain[-1]], E[i], sum(V[c] for c in chain), max(A[c] for c in chain)))
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame({"start": _from_days([r[0] for r in rows]),
                         "end": _from_days([r[1] for r in rows]),
                         "val": [r[2] for r in rows], "avail": _from_days([r[3] for r in rows])})


def build_annuals(f: pd.DataFrame) -> pd.DataFrame:
    """Exercices complets (340 à 390 jours), première valeur publiée."""
    cols = ["start", "end", "val", "avail"]
    f = f.dropna(subset=["start"])
    if f.empty:
        return pd.DataFrame(columns=cols)
    days = (f["end"] - f["start"]).dt.days + 1
    a = f[(days >= Y_RANGE[0]) & (days <= Y_RANGE[1])]
    a = a.sort_values("filed", kind="mergesort").drop_duplicates("end", keep="first")
    return pd.DataFrame({"start": a["start"].values, "end": a["end"].values,
                         "val": a["val"].astype(float).values,
                         "avail": a["filed"].values}).sort_values("end").reset_index(drop=True)


def _with_annuals(ttm: pd.DataFrame, annual: pd.DataFrame) -> pd.DataFrame:
    """Ajoute les exercices publiés. À date de fin égale, le chiffre annuel publié l'emporte
    sur la somme de quatre trimestres : il est directement déclaré et, après une
    republication, il est sur la nouvelle base comptable."""
    if annual is None or not len(annual):
        return ttm
    a = annual[["start", "end", "val", "avail"]].assign(_p=0)
    both = pd.concat([a, ttm.assign(_p=1)], ignore_index=True)
    both = both.sort_values(["end", "_p"], kind="mergesort")
    return both.drop_duplicates("end", keep="first").drop(columns="_p").reset_index(drop=True)


def build_instants(f: pd.DataFrame) -> pd.DataFrame:
    f = f.sort_values(["filed"], kind="mergesort").drop_duplicates("end", keep="first")
    return pd.DataFrame({"end": f["end"].values, "val": f["val"].astype(float).values,
                         "avail": f["filed"].values}).sort_values("end").reset_index(drop=True)


def _nearest(sorted_dates: list, target: pd.Timestamp, tol_days: int) -> int | None:
    if not sorted_dates:
        return None
    i = bisect_left(sorted_dates, target)
    best, best_gap = None, None
    for j in (i - 1, i):
        if 0 <= j < len(sorted_dates):
            gap = abs((sorted_dates[j] - target).days)
            if gap <= tol_days and (best_gap is None or gap < best_gap):
                best, best_gap = j, gap
    return best


# ----------------------------------------------------------------------------
# Tables par société
# ----------------------------------------------------------------------------

class Series:
    """Tableaux numpy pour des recherches rapides à une date de connaissance donnée."""

    def __init__(self, df: pd.DataFrame):
        df = df.sort_values("end").reset_index(drop=True)
        self.end = df["end"].values.astype("datetime64[D]")
        self.start = df["start"].values.astype("datetime64[D]") if "start" in df else None
        self.val = df["val"].values.astype(float)
        self.avail = df["avail"].values.astype("datetime64[D]")
        self.tags = df["tag"].values if "tag" in df else None

    def __len__(self) -> int:
        return len(self.end)

    def latest(self, d: np.datetime64) -> int | None:
        idx = np.nonzero(self.avail <= d)[0]
        return int(idx[np.argmax(self.end[idx])]) if len(idx) else None

    def near(self, target: np.datetime64, d: np.datetime64, tol: int) -> int | None:
        ok = (self.avail <= d) & (np.abs((self.end - target).astype(int)) <= tol)
        idx = np.nonzero(ok)[0]
        if not len(idx):
            return None
        return int(idx[np.argmin(np.abs((self.end[idx] - target).astype(int)))])


MERGED = "fusion"


def _merge(per_tag: list[tuple[int, str, pd.DataFrame]]) -> pd.DataFrame:
    frames = []
    for rank, tag, df in per_tag:
        d = df.copy()
        d["_rank"] = rank
        d["tag"] = tag
        frames.append(d)
    allq = pd.concat(frames, ignore_index=True)
    sort = ["end", "_rank"] + (["derived"] if "derived" in allq else [])
    allq = allq.sort_values(sort, kind="mergesort").drop_duplicates("end", keep="first")
    return allq.drop(columns="_rank").reset_index(drop=True)


def build_concept(sub: pd.DataFrame, concept: str, spec: dict):
    """Séries d'un concept à partir de faits dédoublonnés (une valeur par période)."""
    per_tag = []
    for rank, tag in enumerate(spec["tags"]):
        t = sub[sub["tag"] == tag]
        if t.empty:
            continue
        if spec["kind"] in ("instant", "evidence"):
            inst = build_instants(t)
            if len(inst):
                per_tag.append((rank, tag, inst))
        else:
            q = build_quarters(t, additive=concept not in NON_ADDITIVE,
                               nonneg=concept in NON_NEGATIVE)
            if len(q) or len(build_annuals(t)):
                per_tag.append((rank, tag, q))
    if not per_tag:
        return None, None
    # Série fusionnée : les sociétés changent parfois d'étiquette d'une année à
    # l'autre. Pour chaque date de fin, l'étiquette prioritaire l'emporte.
    merged = _merge(per_tag)
    base = [(MERGED, Series(merged))] + [(tg, Series(x)) for _, tg, x in per_tag]
    ttm_lists = None
    if spec["kind"] == "duration" and concept not in NON_ADDITIVE:
        # Exercices complets : un chiffre annuel est aussi un 12 mois glissants.
        # Il sert quand un rapport trimestriel manque dans les données XBRL.
        annual = {tg: build_annuals(sub[sub["tag"] == tg]) for _, tg, _ in per_tag}
        ann_merged = _merge([(rk, tg, annual[tg]) for rk, tg, _ in per_tag
                             if len(annual[tg])]) if any(len(a) for a in annual.values()) \
            else pd.DataFrame(columns=["start", "end", "val", "avail"])
        lists = []
        for tg, x, a in [(MERGED, merged, ann_merged)] + \
                [(tg, x, annual[tg]) for _, tg, x in per_tag]:
            ttm = _with_annuals(build_ttm(x), a)
            if len(ttm):
                lists.append((tg, Series(ttm)))
        ttm_lists = lists or None
    return base, ttm_lists


def _keys(df: pd.DataFrame) -> pd.Series:
    start = df["start"].dt.strftime("%Y%m%d").fillna("-") if "start" in df else "-"
    return df["tag"].astype(str) + "|" + start + "|" + df["end"].dt.strftime("%Y%m%d")


def restatements(facts: pd.DataFrame) -> list[tuple[pd.Timestamp, set]]:
    """Dates auxquelles une valeur déjà publiée est republiée différemment, avec les
    concepts touchés."""
    f = facts.assign(_k=_keys(facts)).sort_values(["_k", "filed", "accn"], kind="mergesort")
    prev = f.groupby("_k")["val"].shift(1)
    same_key = f["_k"].eq(f["_k"].shift(1))
    diff = (f["val"] - prev).abs() > RESTATE_TOL * prev.abs().clip(lower=1.0)
    hit = f[same_key & diff]
    out: dict = {}
    for d, c in zip(hit["filed"].dt.normalize(), hit["concept"]):
        out.setdefault(d, set()).add(c)
    return sorted(out.items())


def as_of(facts: pd.DataFrame, r: pd.Timestamp) -> pd.DataFrame:
    """Pour chaque période : dernière valeur publiée au plus tard le jour r ; à défaut
    (période publiée après r), la première valeur publiée."""
    f = facts.assign(_k=_keys(facts)).sort_values(["filed", "accn"], kind="mergesort")
    known = f[f["filed"] <= r].drop_duplicates("_k", keep="last")
    later = f[~f["_k"].isin(known["_k"])].drop_duplicates("_k", keep="first")
    return pd.concat([known, later], ignore_index=True).drop(columns="_k")


class Company:
    """Fondamentaux d'une société, tels que connus à chaque date.

    Version 0 : première valeur publiée de chaque période. À chaque date où une valeur est
    republiée (cession d'activité, changement de norme…), les concepts touchés sont
    reconstruits avec la dernière version connue à cette date. Un état à la date d utilise
    la dernière version antérieure ou égale à d : aucune information future n'est utilisée,
    et les comparaisons d'une année sur l'autre restent sur une base homogène.
    """

    def __init__(self, facts: pd.DataFrame, concepts: dict):
        self.concepts = concepts
        self.ttm: dict = {}
        self.quarters: dict = {}
        self.instants: dict = {}
        self.versions: list = []
        if facts.empty:
            self.event_dates = []
            return
        facts = facts.copy()
        facts["filed"] = pd.to_datetime(facts["filed"]).dt.normalize()
        ff = first_filed(facts)
        ttm, quarters, instants = {}, {}, {}
        for concept, spec in concepts.items():
            self._build_into(ff[ff["concept"] == concept], concept, spec, ttm, quarters, instants)
        self.versions.append((np.datetime64("1900-01-01", "D"), ttm, quarters, instants))
        for r, touched in restatements(facts):
            ttm, quarters, instants = dict(ttm), dict(quarters), dict(instants)
            for concept in touched:
                if concept not in concepts:
                    continue
                for d in (ttm, quarters, instants):
                    d.pop(concept, None)
                sub = as_of(facts[facts["concept"] == concept], r)
                self._build_into(sub, concept, concepts[concept], ttm, quarters, instants)
            self.versions.append((np.datetime64(r.date(), "D"), ttm, quarters, instants))
        self.version_dates = [v[0] for v in self.versions]
        self.event_dates = sorted(facts["filed"].unique())
        self._use(np.datetime64("2200-01-01", "D"))

    @staticmethod
    def _build_into(sub, concept, spec, ttm, quarters, instants):
        base, ttm_lists = build_concept(sub, concept, spec)
        if base is None:
            return
        if spec["kind"] in ("instant", "evidence"):
            instants[concept] = base
        else:
            quarters[concept] = base
        if ttm_lists:
            ttm[concept] = ttm_lists

    def _use(self, d: np.datetime64) -> None:
        i = bisect_left(self.version_dates, d + np.timedelta64(1, "D")) - 1
        _, self.ttm, self.quarters, self.instants = self.versions[max(i, 0)]

    # -- sélection d'étiquettes -------------------------------------------------
    @staticmethod
    def _pick(series_list, d):
        """Étiquette ayant la donnée la plus récente ; priorité en cas d'égalité."""
        best = None
        for rank, (tag, s) in enumerate(series_list or []):
            i = s.latest(d)
            if i is None:
                continue
            key = (s.end[i], -rank)
            if best is None or key > best[0]:
                best = (key, tag, s, i)
        return None if best is None else best[1:]

    def ttm_now(self, concept, d):
        p = self._pick(self.ttm.get(concept), d)
        if p is None:
            return None
        tag, s, i = p
        if (d - s.end[i]).astype(int) > STALE_TTM_DAYS:
            return None
        return tag, s, i

    def ttm_year_ago(self, concept, tag, end, d):
        target = end - np.timedelta64(365, "D")
        lists = self.ttm.get(concept) or []
        ordered = sorted(lists, key=lambda x: x[0] != tag)  # même étiquette d'abord
        for t, s in ordered:
            j = s.near(target, d, YEAR_TOL)
            if j is not None:
                return s.val[j], t != tag
        return None, False

    def quarter_yoy(self, concept, tag, end, d):
        """Croissance sur un an du trimestre finissant à `end` et du trimestre précédent."""
        qs = dict(self.quarters.get(concept) or [])
        s = qs.get(tag)
        if s is None:
            return None, None
        i0 = s.near(end, d, 3)
        if i0 is None:
            return None, None

        def yoy(i):
            j = s.near(s.end[i] - np.timedelta64(365, "D"), d, YEAR_TOL)
            if j is None or s.val[j] <= 0:
                return None
            return s.val[i] / s.val[j] - 1.0

        g0 = yoy(i0)
        i1 = s.near(s.start[i0] - np.timedelta64(1, "D"), d, 7)
        g1 = yoy(i1) if i1 is not None else None
        return g0, g1

    def instant_at(self, concept, bs_end, d, tol=3):
        for tag, s in self.instants.get(concept) or []:
            j = s.near(bs_end, d, tol)
            if j is not None:
                return s.val[j], tag
        return None, None

    def instant_recent(self, concept, bs_end, d, max_age=200):
        """Dernière valeur connue à d, datée au plus `max_age` jours avant le bilan."""
        lst = self.instants.get(concept) or []
        if not lst:
            return None, None
        s = lst[0][1]          # série fusionnée
        ok = (s.avail <= d) & (s.end <= bs_end) & \
            ((bs_end - s.end).astype(int) <= max_age)
        idx = np.nonzero(ok)[0]
        if not len(idx):
            return None, None
        j = int(idx[np.argmax(s.end[idx])])
        return s.val[j], s.end[j]

    def material_interest(self, d, assets, threshold=0.003):
        """Charges d'intérêts significatives (> 0,3 % des actifs) : il existe une dette."""
        ie = self.ttm_now("interest_expense", d)
        if ie is None or not assets:
            return False
        return abs(ie[1].val[ie[2]]) > threshold * assets

    def has_debt_evidence(self, d, years=2):
        lst = self.instants.get("debt_flows") or []
        if not lst:
            return False
        s = lst[0][1]
        ok = (s.avail <= d) & (s.end >= d - np.timedelta64(365 * years, "D")) & (s.val > 0)
        return bool(ok.any())

    # -- état à une date --------------------------------------------------------
    def state(self, d: np.datetime64) -> dict:
        self._use(d)
        out: dict = {"known_date": pd.Timestamp(d)}
        flags: list[str] = []

        # Bilan : date de référence = dernier total des actifs connu
        assets_p = self._pick(self.instants.get("assets"), d)
        assets = bs_end = None
        if assets_p:
            _, s, i = assets_p
            assets, bs_end = s.val[i], s.end[i]
            if (d - bs_end).astype(int) > STALE_TTM_DAYS:
                assets = bs_end = None
        out["assets"] = assets
        out["bs_end"] = pd.Timestamp(bs_end) if bs_end is not None else None

        # Chiffre d'affaires
        rev = self.ttm_now("revenue", d)
        if rev:
            tag, s, i = rev
            out["revenue_ttm"] = s.val[i]
            out["quarter_end"] = pd.Timestamp(s.end[i])
            prev, mixed = self.ttm_year_ago("revenue", tag, s.end[i], d)
            out["revenue_ttm_prev"] = prev
            if mixed:
                flags.append("CA : étiquettes XBRL différentes entre les deux années")
            g0, g1 = self.quarter_yoy("revenue", tag, s.end[i], d)
            out["revenue_q_yoy"] = g0
            out["revenue_q_yoy_prev"] = g1
            out["revenue_tag"] = tag
            mq = dict(self.quarters.get("revenue") or []).get(MERGED)
            if tag == MERGED and mq is not None and mq.tags is not None:
                j = mq.near(s.end[i], d, 3)
                out["revenue_tag"] = mq.tags[j] if j is not None else tag

        # Résultat opérationnel (repli : résultat avant impôts)
        oi = self.ttm_now("operating_income", d)
        oi_concept = "operating_income"
        if oi is None:
            oi = self.ttm_now("pretax_income", d)
            oi_concept = "pretax_income"
        if oi:
            tag, s, i = oi
            out["oi_ttm"] = s.val[i]
            out["oi_ttm_prev"], _ = self.ttm_year_ago(oi_concept, tag, s.end[i], d)
            if oi_concept == "pretax_income":
                # EBIT ≈ résultat avant impôts + charges d'intérêts, sur les mêmes périodes
                ie = self.ttm_now("interest_expense", d)
                if ie and ie[1].end[ie[2]] == s.end[i]:
                    ie_tag, ie_s, ie_i = ie
                    out["oi_ttm"] += abs(ie_s.val[ie_i])
                    prev_ie, _ = self.ttm_year_ago("interest_expense", ie_tag, ie_s.end[ie_i], d)
                    if out["oi_ttm_prev"] is not None and prev_ie is not None:
                        out["oi_ttm_prev"] += abs(prev_ie)
                    else:
                        out["oi_ttm_prev"] = None
                    flags.append("Résultat opérationnel absent : avant impôts + intérêts utilisé")
                else:
                    flags.append("Résultat opérationnel absent : résultat avant impôts utilisé")

        # Marge brute : étiquette dédiée, sinon CA - coût des ventes sur la même période
        gp = self.ttm_now("gross_profit", d)
        if gp:
            out["gross_profit_ttm"] = gp[1].val[gp[2]]
            out["gross_profit_ttm_prev"], _ = self.ttm_year_ago(
                "gross_profit", gp[0], gp[1].end[gp[2]], d)
        elif rev:
            cor = self.ttm_now("cost_of_revenue", d)
            if cor and cor[1].end[cor[2]] == rev[1].end[rev[2]]:
                out["gross_profit_ttm"] = out["revenue_ttm"] - cor[1].val[cor[2]]
                cor_prev, _ = self.ttm_year_ago("cost_of_revenue", cor[0], cor[1].end[cor[2]], d)
                if out.get("revenue_ttm_prev") is not None and cor_prev is not None:
                    out["gross_profit_ttm_prev"] = out["revenue_ttm_prev"] - cor_prev

        # Actifs un an plus tôt (variation de la rentabilité)
        if bs_end is not None:
            v, _ = self.instant_at("assets", bs_end - np.timedelta64(365, "D"), d, tol=YEAR_TOL)
            out["assets_prev"] = v

        # Surprise de résultats standardisée (Bernard et Thomas) sur le résultat net
        # trimestriel : variation sur un an du dernier trimestre, divisée par l'écart-type
        # des 8 variations précédentes.
        out["sue"], out["sue_quarter"] = self.sue(d)

        for concept, key in (("net_income", "ni_ttm"), ("cfo", "cfo_ttm"),
                             ("capex", "capex_ttm"), ("dna", "dna_ttm")):
            p = self.ttm_now(concept, d)
            out[key] = p[1].val[p[2]] if p else None

        # Dette et trésorerie, alignées sur la date du bilan
        if bs_end is not None:
            cash, _ = self.instant_at("cash", bs_end, d)
            sti, _ = self.instant_at("short_term_investments", bs_end, d)
            out["cash"] = (cash or 0.0) + (sti or 0.0) if cash is not None else None
            dtl, _ = self.instant_at("debt_total_lt", bs_end, d)
            dnc, _ = self.instant_at("debt_noncurrent", bs_end, d)
            dc, _ = self.instant_at("debt_current", bs_end, d)
            stb, _ = self.instant_at("short_term_borrowings", bs_end, d)
            if dtl is None and dnc is None:
                # Certaines sociétés ne détaillent la dette à long terme qu'une fois par an :
                # on reprend le dernier montant publié (au plus 200 jours avant le bilan).
                v, when = self.instant_recent("debt_total_lt", bs_end, d)
                if v is None:
                    v2, when = self.instant_recent("debt_noncurrent", bs_end, d)
                    if v2 is not None:
                        dnc = v2
                else:
                    dtl = v
                if when is not None:
                    flags.append(f"Dette à long terme : dernier montant publié ({pd.Timestamp(when).date()})")
            if dtl is not None:
                debt = dtl + (stb or 0.0)
            elif dnc is not None or dc is not None:
                debt = (dnc or 0.0) + (dc or 0.0) + (stb or 0.0)
            elif stb is not None:
                debt = stb
            elif self.has_debt_evidence(d) or self.material_interest(d, assets):
                debt = None
                flags.append("Dette introuvable dans les données XBRL (inconnue)")
            else:
                debt = 0.0
                flags.append("Aucune dette déclarée : supposée nulle")
            out["debt"] = debt

        # Nombre d'actions : page de garde, sinon bilan, sinon moyenne diluée du trimestre
        shares = shares_date = None
        p = self._pick(self.instants.get("shares_outstanding"), d)
        if p:
            _, s, i = p
            if bs_end is None or s.end[i] >= bs_end - np.timedelta64(30, "D"):
                shares, shares_date = s.val[i], s.end[i]
        if shares is None and bs_end is not None:
            v, _ = self.instant_at("shares_outstanding_gaap", bs_end, d)
            if v:
                shares, shares_date = v, bs_end
        dil = self._pick(self.quarters.get("diluted_shares"), d)
        if dil is not None:
            _, s, i = dil
            # Plusieurs catégories d'actions : la page de garde n'en donne souvent qu'une.
            if shares is None or shares < 0.7 * s.val[i]:
                if shares is not None:
                    flags.append("Actions : page de garde incomplète (plusieurs catégories)")
                shares, shares_date = s.val[i], s.end[i]
                flags.append("Actions : moyenne diluée du trimestre utilisée")
        out["shares"] = shares
        out["shares_date"] = pd.Timestamp(shares_date) if shares_date is not None else None
        out["flags"] = " | ".join(flags)
        return out

    def sue(self, d: np.datetime64):
        lst = self.quarters.get("net_income")
        if not lst:
            return None, None
        s = lst[0][1]
        ok = np.nonzero(s.avail <= d)[0]
        if not len(ok):
            return None, None
        ends = s.end[ok]
        vals = s.val[ok]
        order = np.argsort(ends)
        ends, vals = ends[order], vals[order]
        if (d - ends[-1]).astype(int) > STALE_TTM_DAYS:
            return None, None
        changes = []
        for k in range(len(ends) - 1, -1, -1):
            target = ends[k] - np.timedelta64(365, "D")
            gap = np.abs((ends - target).astype(int))
            j = int(np.argmin(gap))
            if gap[j] <= YEAR_TOL and j != k:
                changes.append(vals[k] - vals[j])
            else:
                changes.append(None)
            if len(changes) >= 9:
                break
        if not changes or changes[0] is None:
            return None, None
        hist = [c for c in changes[1:] if c is not None]
        if len(hist) < 4:
            return None, None
        sd = float(np.std(hist, ddof=1))
        if sd <= 0:
            return None, None
        return float(changes[0] / sd), pd.Timestamp(ends[-1])

    def states(self) -> list[dict]:
        out = []
        for d in self.event_dates:
            out.append(self.state(np.datetime64(pd.Timestamp(d).date(), "D")))
        return out


STATE_COLUMNS = ["known_date", "quarter_end", "bs_end", "revenue_ttm", "revenue_ttm_prev",
                 "revenue_q_yoy", "revenue_q_yoy_prev", "revenue_tag", "oi_ttm", "oi_ttm_prev",
                 "gross_profit_ttm", "gross_profit_ttm_prev", "ni_ttm", "cfo_ttm", "capex_ttm",
                 "dna_ttm", "assets", "assets_prev", "cash", "debt", "shares", "shares_date",
                 "sue", "sue_quarter", "flags"]


def company_states(facts: pd.DataFrame, concepts: dict) -> pd.DataFrame:
    comp = Company(facts, concepts)
    rows = comp.states()
    df = pd.DataFrame(rows)
    for c in STATE_COLUMNS:
        if c not in df.columns:
            df[c] = None
    df = df[STATE_COLUMNS]
    for c in ("known_date", "quarter_end", "bs_end", "shares_date", "sue_quarter"):
        df[c] = pd.to_datetime(df[c])
    for c in STATE_COLUMNS:
        if c not in ("known_date", "quarter_end", "bs_end", "shares_date", "sue_quarter",
                     "revenue_tag", "flags"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def safe_div(a, b):
    try:
        if a is None or b is None or (isinstance(b, float) and math.isnan(b)) or b == 0:
            return None
        r = a / b
        return None if (isinstance(r, float) and math.isnan(r)) else r
    except TypeError:
        return None
