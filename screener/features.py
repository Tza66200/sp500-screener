"""Calcul des mesures à une date donnée (cours + fondamentaux connus à cette date)."""
from __future__ import annotations

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
    "mom_12_1":         ("momentum", +1, False),
    "mom_6_1":          ("momentum", +1, False),
    "gp_assets":        ("quality",  +1, True),
    "accruals":         ("quality",  -1, True),
    "leverage":         ("quality",  -1, True),
    "fcf_yield":        ("value",    +1, True),
    "ebit_ev":          ("value",    +1, True),
    "vol_12m":          ("risk",     -1, False),
}

METRIC_LABELS = {
    "rev_growth": "Croissance du CA sur 1 an (12 mois glissants)",
    "rev_accel": "Accélération du CA (trimestre vs trimestre précédent, sur 1 an)",
    "oi_change_assets": "Variation du résultat opérationnel / actifs",
    "mom_12_1": "Rendement 12 mois hors dernier mois",
    "mom_6_1": "Rendement 6 mois hors dernier mois",
    "gp_assets": "Marge brute / actifs",
    "accruals": "(Bénéfice net - cash-flow d'exploitation) / actifs",
    "leverage": "Dette nette / EBITDA",
    "fcf_yield": "Rendement du free cash-flow",
    "ebit_ev": "EBIT / valeur d'entreprise",
    "vol_12m": "Volatilité annualisée sur 12 mois",
}

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
    mcap = f["market_cap"].where(f["market_cap"] > 0)
    f["fcf_yield"] = (f["cfo_ttm"] - f["capex_ttm"]) / mcap
    ev = mcap + f["debt"].fillna(0) - f["cash"].fillna(0)
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
    feats["asof"] = asof
    return feats
