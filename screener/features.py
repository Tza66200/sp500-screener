"""Calcul des mesures à une date donnée (cours + fondamentaux connus à cette date)."""
from __future__ import annotations

import itertools
import logging
import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import universe as U

log = logging.getLogger(__name__)

# Mesures : (facteur, sens, comparaison sectorielle)
METRICS = {
    "rev_growth":       ("growth",   +1, True),
    "rev_accel":        ("growth",   +1, True),
    "oi_change_assets": ("growth",   +1, True),
    "sue":              ("earnings", +1, False),
    "ear":              ("earnings", +1, False),
    "gp_change":        ("earnings", +1, True),
    "mom_12_1":         ("momentum", +1, False),
    "mom_6_1":          ("momentum", +1, False),
    "gp_assets":        ("quality",  +1, True),
    "accruals":         ("quality",  -1, True),
    "leverage":         ("quality",  -1, True),
    "fcf_yield":        ("value",    +1, True),
    "ebit_ev":          ("value",    +1, True),
    "vol_12m":          ("risk",     -1, False),
    "net_iss":          ("buyback",  -1, True),
    "vol_12m_sec":      ("risk_sec", -1, True),
}

METRIC_LABELS = {
    "rev_growth": "Croissance du CA sur 1 an (12 mois glissants)",
    "rev_accel": "Accélération du CA (trimestre vs trimestre précédent, sur 1 an)",
    "oi_change_assets": "Variation du résultat opérationnel / actifs",
    "sue": "Surprise de résultats standardisée (dernier trimestre)",
    "ear": "Réaction du cours aux derniers résultats (3 jours, vs équipondéré)",
    "gp_change": "Variation sur un an de la marge brute / actifs",
    "mom_12_1": "Rendement 12 mois hors dernier mois",
    "mom_6_1": "Rendement 6 mois hors dernier mois",
    "gp_assets": "Marge brute / actifs",
    "accruals": "(Bénéfice net - cash-flow d'exploitation) / actifs",
    "leverage": "Dette nette / EBITDA",
    "fcf_yield": "Rendement du free cash-flow",
    "ebit_ev": "EBIT / valeur d'entreprise",
    "vol_12m": "Volatilité annualisée sur 12 mois",
    "net_iss": "Variation du nombre d'actions sur 1 an (rachats nets)",
    "vol_12m_sec": "Volatilité annualisée sur 12 mois, comparée au secteur",
}

# Contrôle du nombre d'actions : rotation quotidienne moyenne (volume en dollars sur
# capitalisation) hors de cette plage, ou nombre d'actions corrigé des fractionnements
# multiplié ou divisé par plus de SHARES_JUMP par rapport aux deux années précédentes :
# la capitalisation est tenue pour inconnue.
TURNOVER_RANGE = (2e-4, 0.5)
SHARES_JUMP = 4.0
NET_ISS_RANGE = (0.5, 3.0)   # au-delà, variation sur un an tenue pour une erreur de données
DILUTED_FLAG = "moyenne diluée"
_NO_DATE = np.int64(-10 ** 9)
# Yahoo range parmi les fractionnements les scissions (distribution des actions d'une filiale),
# avec pour ratio la baisse du cours : 1,241 pour FedEx le 2026-06-01, 1,272 pour Becton
# Dickinson le 2026-02-10. Le cours ajusté en tient compte, mais le nombre d'actions de la
# société, lui, ne change pas. Pour les rachats nets, un ratio n'est donc appliqué que si les
# nombres d'actions publiés le confirment (voir real_split_factor).
SPLIT_LOOKBACK_DAYS = 100    # un nombre daté peu avant peut déjà être sur la nouvelle base
SPLIT_EARLY_MIN = 1.25       # ... admis seulement pour un fractionnement d'au moins 5 pour 4


def _days(ts) -> int:
    return int(np.datetime64(pd.Timestamp(ts).date(), "D").astype(np.int64))


def split_factors(splits: tuple | None, days: np.ndarray) -> np.ndarray:
    """Produit des fractionnements postérieurs à chaque jour (comme Context.split_factor).
    `splits` : (jours des fractionnements, produits cumulés depuis la fin)."""
    days = np.atleast_1d(np.asarray(days, dtype=np.int64))
    if splits is None:
        return np.ones(len(days))
    d, suf = splits
    k = np.searchsorted(d, days, side="right")
    out = np.ones(len(days))
    ok = k < len(d)
    out[ok] = suf[k[ok]]
    return out


def real_split_factor(sh: np.ndarray, sd: np.ndarray, idx: np.ndarray, splits: tuple | None,
                      j: int, k: int, day: int) -> float:
    """Produit des fractionnements réels entre les nombres d'actions des états j et k.

    Un fractionnement de la liste Yahoo est tenu pour réel si les nombres d'actions publiés
    font, autour de sa date, un saut plus proche de son ratio que de 1 ; sinon c'est une
    scission (ou une donnée fausse) et le nombre d'actions n'a pas changé.
    1. Le saut est d'abord cherché entre les deux nombres qui encadrent la date. Si plusieurs
       fractionnements tombent entre les deux mêmes nombres, on retient la combinaison de
       ratios qui explique le mieux le saut (aucune, si c'est « pas de saut »).
    2. À défaut, il est cherché un rapport plus tôt, quand le nombre daté juste avant (de moins
       de SPLIT_LOOKBACK_DAYS jours) est déjà sur la nouvelle base : une moyenne diluée publiée
       après le fractionnement est corrigée même pour un trimestre clos avant. Réservé aux
       ratios d'au moins SPLIT_EARLY_MIN (ou leur inverse) : en dessous, une simple variation
       trimestrielle du nombre d'actions suffirait à « confirmer » un petit ratio de scission.
    Seuls comptent les fractionnements déjà intervenus à `day`.

    `idx` : états utilisables (nombre valide, même source que k), tous antérieurs ou égaux à k.
    """
    if splits is None:
        return 1.0
    d, suf = splits
    ratios = suf / np.append(suf[1:], 1.0)
    use = np.nonzero((d <= day) & (d > sd[j]) & (d < sd[k] + SPLIT_LOOKBACK_DAYS) &
                     np.isfinite(ratios) & (ratios > 0))[0]
    if not len(use):
        return 1.0
    logs = {int(e): math.log(ratios[e]) for e in use}
    # Un état par date de nombre d'actions (le dernier connu), dates croissantes
    order = np.lexsort((idx, sd[idx]))
    idx = idx[order]
    pts = idx[np.append(sd[idx][1:] != sd[idx][:-1], True)]
    dates = sd[pts]
    jumps = np.diff(np.log(sh[pts]))             # saut entre pts[q] et pts[q + 1]
    pj, pk = int(np.searchsorted(dates, sd[j])), int(np.searchsorted(dates, sd[k]))
    explained = np.zeros(len(jumps))             # part de chaque saut attribuée à un ratio
    found: dict[int, int] = {}                   # fractionnement réel -> saut où il est constaté
    before: dict[int, list[int]] = {}            # fractionnements par dernier nombre daté avant
    for e in logs:
        before.setdefault(int(np.searchsorted(dates, d[e], side="left")) - 1, []).append(e)
    pending = []
    for q, events in before.items():
        best: tuple = ()
        if 0 <= q < len(jumps):
            events = sorted(events, key=lambda e: -abs(logs[e]))[:6]
            best_err = abs(jumps[q])
            for n in range(1, len(events) + 1):
                for combo in itertools.combinations(events, n):
                    err = abs(jumps[q] - sum(logs[e] for e in combo))
                    if err < best_err:
                        best, best_err = combo, err
            for e in best:
                found[e] = q
                explained[q] += logs[e]
        pending += [e for e in before[q] if e not in best]
    early_min = math.log(SPLIT_EARLY_MIN) - 1e-9
    for e in sorted(pending, key=lambda e: -abs(logs[e])):
        q = int(np.searchsorted(dates, d[e], side="left")) - 1
        if abs(logs[e]) >= early_min and 1 <= q <= len(jumps) and \
                d[e] - dates[q] < SPLIT_LOOKBACK_DAYS:
            rest = jumps[q - 1] - explained[q - 1]
            if abs(rest - logs[e]) < abs(rest):
                found[e] = q - 1
                explained[q - 1] += logs[e]
    return float(np.prod([ratios[e] for e, q in found.items() if pj <= q < pk]))


def net_issuance(hist: tuple | None, splits: tuple | None, day: int) -> float:
    """Variation sur un an du nombre d'actions, corrigée des fractionnements réels : dernier
    nombre connu à `day` (daté de moins de 200 jours) comparé au nombre connu un an plus tôt
    (à 45 jours près), de même source (page de garde ou moyenne diluée). Les scissions, que
    Yahoo présente comme des fractionnements, ne modifient pas le nombre d'actions : elles
    sont écartées (voir real_split_factor)."""
    if hist is None:
        return np.nan
    u, sh, sd, dil = hist
    k = int(np.searchsorted(u, day, side="right")) - 1
    if k < 0 or not (np.isfinite(sh[k]) and sh[k] > 0) or sd[k] < 0 or day - sd[k] > 200:
        return np.nan
    gap = np.abs(sd[:k + 1] - (sd[k] - 365))
    usable = (sd[:k + 1] >= 0) & np.isfinite(sh[:k + 1]) & (sh[:k + 1] > 0) & \
        (dil[:k + 1] == dil[k])
    ok = usable & (gap <= 45)
    if not ok.any():
        return np.nan
    cand = np.nonzero(ok)[0]
    j = int(cand[gap[cand] == gap[cand].min()][-1])
    ratio = sh[k] / (sh[j] * real_split_factor(sh, sd, np.nonzero(usable)[0], splits, j, k, day))
    if not (NET_ISS_RANGE[0] <= ratio <= NET_ISS_RANGE[1]):
        return np.nan
    return float(ratio - 1.0)


def shares_suspect(hist: tuple | None, splits: tuple | None, day: int, mcap: float,
                   dvol: float) -> bool:
    """Nombre d'actions incohérent avec les volumes échangés ou avec son propre passé."""
    if np.isfinite(mcap) and mcap > 0 and np.isfinite(dvol) and dvol > 0:
        turn = dvol / mcap
        if turn < TURNOVER_RANGE[0] or turn > TURNOVER_RANGE[1]:
            return True
    if hist is None:
        return False
    u, sh, sd, _ = hist
    k = int(np.searchsorted(u, day, side="right")) - 1
    if k < 0 or not (np.isfinite(sh[k]) and sh[k] > 0) or sd[k] < 0:
        return False
    h = np.nonzero((u <= day - 90) & (u >= day - 730) & np.isfinite(sh) & (sh > 0) &
                   (sd >= 0))[0]
    if len(h) < 2:
        return False
    now = sh[k] * split_factors(splits, sd[k])[0]
    past = float(np.median(sh[h] * split_factors(splits, sd[h])))
    ratio = now / past if past > 0 else np.nan
    return bool(np.isfinite(ratio) and (ratio > SHARES_JUMP or ratio < 1 / SHARES_JUMP))

LAG_SKIP = 21     # « hors dernier mois »
LAG_6M = 126
LAG_12M = 252


@dataclass
class Context:
    prices: dict
    states: pd.DataFrame            # cik, usable_date, colonnes d'état (trié)
    info: pd.DataFrame              # ticker -> cik, name, sector
    history: pd.DataFrame           # composition historique
    current: pd.DataFrame           # composition actuelle
    excluded_sectors: list[str]
    earnings: dict = field(default_factory=dict)   # cik -> dates des communiqués de résultats
    market: str = "RSP"                            # référence pour la réaction aux résultats
    logret: pd.DataFrame = field(init=False)
    dollar_vol: pd.DataFrame = field(init=False)
    split_lookup: dict = field(init=False)

    def __post_init__(self):
        adj = self.prices["adj_close"]
        self.logret = np.log(adj / adj.shift(1))
        self.dollar_vol = self.prices["close"] * self.prices["volume"]
        sp = self.prices["splits"]
        self.split_lookup = {t: g.sort_values("date") for t, g in sp.groupby("ticker")}
        st = self.states.copy()
        st["cik"] = st["cik"].astype(float)
        self.states = st.sort_values(["cik", "usable_date"]).reset_index(drop=True)
        self.info = self.info.copy()
        self.info["cik"] = pd.to_numeric(self.info["cik"], errors="coerce").astype(float)
        cal = self.prices["adj_close"].index
        # Position (séance) de chaque communiqué : première séance >= date de dépôt
        self.earn_pos = {float(c): np.asarray(cal.searchsorted(pd.DatetimeIndex(v)), dtype=int)
                         for c, v in self.earnings.items() if len(v)}
        self.adj_values = self.prices["adj_close"].ffill().values
        self.adj_col = {t: j for j, t in enumerate(self.prices["adj_close"].columns)}
        # Historique du nombre d'actions par société et fractionnements par titre (jours)
        self.split_days = {}
        for t, g in self.split_lookup.items():
            d = g["date"].to_numpy().astype("datetime64[D]").astype(np.int64)
            r = g["ratio"].to_numpy(dtype=float)
            self.split_days[t] = (d, np.cumprod(r[::-1])[::-1])
        self.share_hist = {}
        if {"shares", "shares_date", "flags"} <= set(self.states.columns):
            for cik, g in self.states.groupby("cik", sort=False):
                u = g["usable_date"].to_numpy().astype("datetime64[D]").astype(np.int64)
                sd_raw = pd.to_datetime(g["shares_date"]).to_numpy().astype("datetime64[D]")
                sd = np.where(np.isnat(sd_raw), _NO_DATE, sd_raw.astype(np.int64))
                sh = pd.to_numeric(g["shares"], errors="coerce").to_numpy(dtype=float)
                dil = g["flags"].fillna("").astype(str).str.contains(
                    DILUTED_FLAG, regex=False).to_numpy()
                self.share_hist[float(cik)] = (u, sh, sd, dil)

    @property
    def calendar(self) -> pd.DatetimeIndex:
        return self.prices["adj_close"].index

    def pos(self, when: pd.Timestamp) -> int:
        """Position de la dernière séance <= when."""
        return int(self.calendar.searchsorted(pd.Timestamp(when), side="right") - 1)

    def split_factor(self, ticker: str, after: pd.Timestamp) -> float:
        g = self.split_lookup.get(ticker)
        if g is None or pd.isna(after):
            return 1.0
        r = g.loc[g["date"] > after, "ratio"].values
        return float(np.prod(r)) if len(r) else 1.0


def price_features(ctx: Context, p: int, tickers: list[str]) -> pd.DataFrame:
    adj = ctx.prices["adj_close"]
    cols = [t for t in tickers if t in adj.columns]
    out = pd.DataFrame(index=pd.Index(tickers, name="ticker"))
    if p < LAG_12M or not cols:
        return out
    a = adj[cols]
    now = a.iloc[p]
    skip = a.iloc[p - LAG_SKIP]
    out.loc[cols, "price_adj"] = now.values
    out.loc[cols, "price"] = ctx.prices["close"][cols].iloc[p].values
    out.loc[cols, "mom_12_1"] = (skip / a.iloc[p - LAG_12M] - 1).values
    out.loc[cols, "mom_6_1"] = (skip / a.iloc[p - LAG_6M] - 1).values
    window = ctx.logret[cols].iloc[p - LAG_12M + 1:p + 1]
    count = window.notna().sum()
    vol = window.std() * math.sqrt(252)
    out.loc[cols, "vol_12m"] = vol.where(count >= 200).values
    sma = a.iloc[p - 199:p + 1].mean()
    out.loc[cols, "above_sma200"] = (now > sma).where(now.notna()).values
    out.loc[cols, "dollar_vol_63"] = ctx.dollar_vol[cols].iloc[p - 62:p + 1].mean().values
    out.loc[cols, "ret_1y"] = (now / a.iloc[p - LAG_12M] - 1).values
    return out


EAR_MAX_AGE_DAYS = 100


def ear_feature(ctx: Context, p: int, frame: pd.DataFrame) -> pd.Series:
    """Rendement anormal sur 3 séances (veille, jour, lendemain du communiqué de résultats),
    moins celui du S&P 500 équipondéré. Dernier communiqué dont la fenêtre est close à p."""
    out = pd.Series(np.nan, index=frame.index)
    cal = ctx.calendar
    m = ctx.adj_col.get(ctx.market)
    if m is None:
        return out
    px = ctx.adj_values
    for t, cik in frame["cik"].items():
        pos = ctx.earn_pos.get(cik) if pd.notna(cik) else None
        j = ctx.adj_col.get(t)
        if pos is None or j is None:
            continue
        k = np.searchsorted(pos, p - 1, side="right") - 1
        if k < 0:
            continue
        e = pos[k]
        if e < 1 or e + 1 > p or (cal[p] - cal[e]).days > EAR_MAX_AGE_DAYS:
            continue
        a0, a1, m0, m1 = px[e - 1, j], px[e + 1, j], px[e - 1, m], px[e + 1, m]
        if np.isfinite(a0) and np.isfinite(a1) and a0 > 0 and m0 > 0:
            out[t] = (a1 / a0 - 1) - (m1 / m0 - 1)
    return out


def latest_states(ctx: Context, when: pd.Timestamp) -> pd.DataFrame:
    st = ctx.states[ctx.states["usable_date"] <= when]
    return st.groupby("cik", sort=False).tail(1).set_index("cik")


def fundamental_features(ctx: Context, frame: pd.DataFrame, when: pd.Timestamp) -> pd.DataFrame:
    """Ajoute les mesures fondamentales. `frame` contient ticker (index), cik, price."""
    st = latest_states(ctx, when)
    f = frame.join(st, on="cik", rsuffix="_st")
    assets = f["assets"].where(f["assets"] > 0)

    prev = f["revenue_ttm_prev"].where(f["revenue_ttm_prev"] > 0)
    f["rev_growth"] = f["revenue_ttm"] / prev - 1
    f["rev_accel"] = f["revenue_q_yoy"] - f["revenue_q_yoy_prev"]
    f["oi_change_assets"] = (f["oi_ttm"] - f["oi_ttm_prev"]) / assets

    gp = f["gross_profit_ttm"]
    f["gp_fallback"] = gp.isna() & f["oi_ttm"].notna()
    f["gp_assets"] = gp.fillna(f["oi_ttm"]) / assets
    assets_prev = f["assets_prev"].where(f["assets_prev"] > 0)
    gp_prev = f["gross_profit_ttm_prev"].where(~f["gp_fallback"], f["oi_ttm_prev"])
    f["gp_change"] = f["gp_assets"] - gp_prev / assets_prev
    f["accruals"] = (f["ni_ttm"] - f["cfo_ttm"]) / assets

    ebitda = f["oi_ttm"] + f["dna_ttm"].fillna(0)
    net_debt = f["debt"] - f["cash"].fillna(0)
    f["net_debt"] = net_debt
    f["ebitda"] = ebitda
    f["net_debt_ebitda"] = (net_debt / ebitda).where(ebitda > 0)
    lev = pd.Series(np.nan, index=f.index)
    net_cash = net_debt <= 0
    lev[net_cash] = (net_debt / assets)[net_cash] - 10          # trésorerie nette : le mieux
    pos = (net_debt > 0) & (ebitda > 0)
    lev[pos] = (net_debt / ebitda)[pos].clip(upper=50)
    lev[(net_debt > 0) & (ebitda <= 0)] = 1000                  # dette et EBITDA négatif : le pire
    f["leverage"] = lev.where(f["debt"].notna() & assets.notna())

    factor = np.array([ctx.split_factor(t, sd) for t, sd in zip(f.index, f["shares_date"])])
    f["market_cap"] = f["price"] * f["shares"] * factor

    # Rachats nets et contrôle du nombre d'actions
    day = _days(when)
    ciks = pd.to_numeric(f["cik"], errors="coerce").to_numpy(dtype=float)
    caps = pd.to_numeric(f["market_cap"], errors="coerce").to_numpy(dtype=float)
    dvols = pd.to_numeric(f["dollar_vol_63"], errors="coerce").to_numpy(dtype=float) \
        if "dollar_vol_63" in f else np.full(len(f), np.nan)
    iss, sus = np.full(len(f), np.nan), np.zeros(len(f), dtype=bool)
    for i, t in enumerate(f.index):
        if not np.isfinite(ciks[i]):
            continue
        hist, spl = ctx.share_hist.get(float(ciks[i])), ctx.split_days.get(t)
        iss[i] = net_issuance(hist, spl, day)
        sus[i] = shares_suspect(hist, spl, day, caps[i], dvols[i])
    f["net_iss"] = iss
    f["shares_suspect"] = sus
    if sus.any():
        f.loc[sus, "market_cap"] = np.nan
        note = "Nombre d'actions incohérent (volumes échangés ou historique) : capitalisation " \
               "et valorisation tenues pour inconnues"
        f.loc[sus, "flags"] = [" | ".join(x for x in (fl, note) if isinstance(x, str) and x)
                               for fl in f.loc[sus, "flags"]]
    mcap = f["market_cap"].where(f["market_cap"] > 0)
    f["fcf_yield"] = (f["cfo_ttm"] - f["capex_ttm"]) / mcap
    ev = mcap + f["debt"] - f["cash"].fillna(0)      # dette inconnue -> VE inconnue
    f["enterprise_value"] = ev
    f["ebit_ev"] = (f["oi_ttm"] / ev).where(ev > 0)
    f["fundamentals_age_days"] = (pd.Timestamp(when) - f["known_date"]).dt.days
    return f


def universe_frame(ctx: Context, when: pd.Timestamp, live: bool) -> pd.DataFrame:
    """Titres membres de l'indice à la date, avec CIK et secteur."""
    members = ctx.current["ticker"].tolist() if live else U.members_at(ctx.history, ctx.current, when)
    info = ctx.info.reindex(members)
    info.index.name = "ticker"
    return info


def compute(ctx: Context, when: pd.Timestamp, live: bool = False) -> pd.DataFrame:
    p = ctx.pos(when)
    asof = ctx.calendar[p]
    base = universe_frame(ctx, asof, live)
    pf = price_features(ctx, p, list(base.index))
    frame = base.join(pf)
    frame["cik"] = pd.to_numeric(frame["cik"], errors="coerce")
    feats = fundamental_features(ctx, frame, asof)
    feats["ear"] = ear_feature(ctx, p, feats)
    feats["vol_12m_sec"] = feats["vol_12m"] if "vol_12m" in feats else np.nan
    feats["asof"] = asof
    return feats
