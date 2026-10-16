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


def build_quarters(f: pd.DataFrame, additive: bool = True) -> pd.DataFrame:
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


class Company:
    def __init__(self, facts: pd.DataFrame, concepts: dict):
        self.concepts = concepts
        self.ttm: dict[str, list[tuple[str, Series]]] = {}
        self.quarters: dict[str, list[tuple[str, Series]]] = {}
        self.instants: dict[str, list[tuple[str, Series]]] = {}
        facts = facts.copy()
        if facts.empty:
            self.event_dates = []
            return
        ff = first_filed(facts)
        for concept, spec in concepts.items():
            sub = ff[ff["concept"] == concept]
            for tag in spec["tags"]:
                t = sub[sub["tag"] == tag]
                if t.empty:
                    continue
                if spec["kind"] == "instant":
                    inst = build_instants(t)
                    if len(inst):
                        self.instants.setdefault(concept, []).append((tag, Series(inst)))
                else:
                    q = build_quarters(t, additive=concept not in NON_ADDITIVE)
                    if len(q):
                        self.quarters.setdefault(concept, []).append((tag, Series(q)))
                        if concept not in NON_ADDITIVE:
                            ttm = build_ttm(q)
                            if len(ttm):
                                self.ttm.setdefault(concept, []).append((tag, Series(ttm)))
        self.event_dates = sorted(pd.to_datetime(ff["filed"]).dt.normalize().unique())

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

    # -- état à une date --------------------------------------------------------
    def state(self, d: np.datetime64) -> dict:
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
        elif rev:
            cor = self.ttm_now("cost_of_revenue", d)
            if cor and cor[1].end[cor[2]] == rev[1].end[rev[2]]:
                out["gross_profit_ttm"] = out["revenue_ttm"] - cor[1].val[cor[2]]

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
            if dtl is not None:
                debt = dtl + (stb or 0.0)
            elif dnc is not None or dc is not None:
                debt = (dnc or 0.0) + (dc or 0.0) + (stb or 0.0)
            elif stb is not None:
                debt = stb
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

    def states(self) -> list[dict]:
        out = []
        for d in self.event_dates:
            out.append(self.state(np.datetime64(pd.Timestamp(d).date(), "D")))
        return out


STATE_COLUMNS = ["known_date", "quarter_end", "bs_end", "revenue_ttm", "revenue_ttm_prev",
                 "revenue_q_yoy", "revenue_q_yoy_prev", "revenue_tag", "oi_ttm", "oi_ttm_prev",
                 "gross_profit_ttm", "ni_ttm", "cfo_ttm", "capex_ttm", "dna_ttm", "assets",
                 "cash", "debt", "shares", "shares_date", "flags"]


def company_states(facts: pd.DataFrame, concepts: dict) -> pd.DataFrame:
    comp = Company(facts, concepts)
    rows = comp.states()
    df = pd.DataFrame(rows)
    for c in STATE_COLUMNS:
        if c not in df.columns:
            df[c] = None
    df = df[STATE_COLUMNS]
    for c in ("known_date", "quarter_end", "bs_end", "shares_date"):
        df[c] = pd.to_datetime(df[c])
    for c in STATE_COLUMNS:
        if c not in ("known_date", "quarter_end", "bs_end", "shares_date", "revenue_tag", "flags"):
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
