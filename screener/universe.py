"""Univers : membres actuels et historiques du S&P 500, correspondance ticker -> CIK, secteurs."""
from __future__ import annotations

import io
import logging
from datetime import date

import pandas as pd

from . import http
from .config import DATA_DIR

log = logging.getLogger(__name__)

WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
FJA_BASE = "https://raw.githubusercontent.com/fja05680/sp500/master/"
FJA_HISTORY = FJA_BASE + "S%26P%20500%20Historical%20Components%20%26%20Changes%20(Updated).csv"
FJA_CURRENT = FJA_BASE + "sp500.csv"
SEC_TICKERS = "https://www.sec.gov/files/company_tickers.json"


def norm_ticker(t: str) -> str:
    return str(t).strip().upper().replace(".", "-")


def _clean_current(df: pd.DataFrame, source: str) -> pd.DataFrame:
    out = pd.DataFrame({
        "ticker": df["Symbol"].map(norm_ticker),
        "name": df["Security"].astype(str),
        "sector": df["GICS Sector"].astype(str),
        "sub_industry": df["GICS Sub-Industry"].astype(str),
        "cik": pd.to_numeric(df["CIK"], errors="coerce").astype("Int64"),
        "date_added": df.get("Date added", pd.Series(index=df.index, dtype=str)).astype(str),
    })
    out["source"] = source
    return out.drop_duplicates("ticker").reset_index(drop=True)


def fetch_current_constituents() -> pd.DataFrame:
    """Membres actuels : Wikipedia, sinon la copie maintenue par fja05680."""
    try:
        resp = http.get(WIKI_URL, headers={"User-Agent": http.BROWSER_UA})
        tables = pd.read_html(io.StringIO(resp.text), attrs={"id": "constituents"})
        df = _clean_current(tables[0], "wikipedia")
        if len(df) < 480:
            raise ValueError(f"liste Wikipedia incomplète ({len(df)} lignes)")
        return df
    except Exception as exc:  # noqa: BLE001
        log.warning("Wikipedia indisponible (%s) ; repli sur fja05680/sp500.csv", exc)
        resp = http.get(FJA_CURRENT)
        return _clean_current(pd.read_csv(io.StringIO(resp.text)), "fja05680")


def fetch_membership_history() -> pd.DataFrame:
    """Composition historique : une ligne par date de changement, liste de tickers."""
    resp = http.get(FJA_HISTORY)
    df = pd.read_csv(io.StringIO(resp.text))
    df["date"] = pd.to_datetime(df["date"])
    df["tickers"] = df["tickers"].map(lambda s: sorted({norm_ticker(x) for x in str(s).split(",") if x}))
    return df.sort_values("date").reset_index(drop=True)


def members_at(history: pd.DataFrame, current: pd.DataFrame, when: pd.Timestamp) -> list[str]:
    """Membres à une date. Après la dernière date de l'historique, la liste actuelle fait foi
    si la date demandée est postérieure d'au moins 30 jours (l'historique est mis à jour
    tous les deux mois environ)."""
    when = pd.Timestamp(when)
    last = history["date"].iloc[-1]
    if when > last + pd.Timedelta(days=30):
        return sorted(current["ticker"])
    rows = history[history["date"] <= when]
    if rows.empty:
        return []
    return rows["tickers"].iloc[-1]


def all_members_since(history: pd.DataFrame, current: pd.DataFrame, start: str) -> list[str]:
    tickers: set[str] = set(current["ticker"])
    start_ts = pd.Timestamp(start)
    before = history[history["date"] <= start_ts]
    if not before.empty:
        tickers |= set(before["tickers"].iloc[-1])
    for lst in history.loc[history["date"] > start_ts, "tickers"]:
        tickers |= set(lst)
    return sorted(tickers)


def membership_matrix(history: pd.DataFrame, current: pd.DataFrame, dates: pd.DatetimeIndex,
                      tickers: list[str]) -> pd.DataFrame:
    """Matrice booléenne dates x tickers : membre de l'indice à la date."""
    idx = {t: i for i, t in enumerate(tickers)}
    import numpy as np

    mat = np.zeros((len(dates), len(tickers)), dtype=bool)
    for i, d in enumerate(dates):
        for t in members_at(history, current, d):
            j = idx.get(t)
            if j is not None:
                mat[i, j] = True
    return pd.DataFrame(mat, index=dates, columns=tickers)


def fetch_sec_ticker_map() -> pd.DataFrame:
    resp = http.get(SEC_TICKERS, headers={"User-Agent": http.sec_user_agent()})
    data = resp.json()
    rows = [{"ticker": norm_ticker(v["ticker"]), "cik": int(v["cik_str"]), "title": v["title"]}
            for v in data.values()]
    return pd.DataFrame(rows).drop_duplicates("ticker")


def sic_to_sector(sic: int | float | None) -> str | None:
    """Approximation SIC -> secteur GICS, utilisée seulement pour les anciens membres
    absents de la liste actuelle (Wikipedia ne donne le GICS que des membres actuels)."""
    if sic is None or pd.isna(sic):
        return None
    s = int(sic)
    if s == 6798 or 6500 <= s <= 6599:
        return "Real Estate"
    if 6000 <= s <= 6799:
        return "Financials"
    if 100 <= s <= 999 or 2000 <= s <= 2199 or 2840 <= s <= 2844 or 5140 <= s <= 5149 \
            or 5400 <= s <= 5499 or s in (5912, 5331):
        return "Consumer Staples"
    if 1300 <= s <= 1399 or 2900 <= s <= 2999:
        return "Energy"
    if 1000 <= s <= 1499 or 2400 <= s <= 2499 or 2600 <= s <= 2699 or 2800 <= s <= 2829 \
            or 2850 <= s <= 2899 or 3000 <= s <= 3099 or 3200 <= s <= 3399:
        return "Materials"
    if 2830 <= s <= 2836 or 3841 <= s <= 3851 or 8000 <= s <= 8099 or s == 5122:
        return "Health Care"
    if 3570 <= s <= 3579 or 3661 <= s <= 3679 or 3820 <= s <= 3829 or s == 3861 \
            or 7370 <= s <= 7379:
        return "Information Technology"
    if 2700 <= s <= 2799 or 4800 <= s <= 4899 or 7310 <= s <= 7319 or 7810 <= s <= 7829:
        return "Communication Services"
    if 4900 <= s <= 4999:
        return "Utilities"
    if 2200 <= s <= 2399 or 2500 <= s <= 2599 or 3100 <= s <= 3199 or 3630 <= s <= 3639 \
            or 3711 <= s <= 3716 or s == 3873 or 3900 <= s <= 3999 or 5200 <= s <= 5999 \
            or 7000 <= s <= 7299 or 7900 <= s <= 7999:
        return "Consumer Discretionary"
    if 1500 <= s <= 1799 or 3400 <= s <= 3569 or 3580 <= s <= 3699 or 3700 <= s <= 3799 \
            or 3800 <= s <= 3899 or 4000 <= s <= 4799 or 5000 <= s <= 5199 or 7300 <= s <= 7399 \
            or 8100 <= s <= 8999:
        return "Industrials"
    return None


def save_universe(current: pd.DataFrame, history: pd.DataFrame) -> None:
    current.to_parquet(DATA_DIR / "current_constituents.parquet", index=False)
    h = history.copy()
    h["tickers"] = h["tickers"].map(",".join)
    h.to_parquet(DATA_DIR / "membership_history.parquet", index=False)


def load_universe() -> tuple[pd.DataFrame, pd.DataFrame]:
    current = pd.read_parquet(DATA_DIR / "current_constituents.parquet")
    history = pd.read_parquet(DATA_DIR / "membership_history.parquet")
    history["tickers"] = history["tickers"].map(lambda s: s.split(",") if s else [])
    history["date"] = pd.to_datetime(history["date"])
    return current, history


def today() -> date:
    return pd.Timestamp.now(tz="America/New_York").date()
