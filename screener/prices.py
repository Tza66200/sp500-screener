"""Cours quotidiens via yfinance.

Chaque exécution retélécharge l'historique complet : Yahoo réajuste tout l'historique
à chaque dividende ou fractionnement, donc ajouter des jours à une série stockée
créerait des ruptures. Le nombre de requêtes est le même qu'en incrémental.
Si un titre échoue, sa série précédente est conservée et signalée comme ancienne.
"""
from __future__ import annotations

import logging
import time

import numpy as np
import pandas as pd

from .config import DATA_DIR

log = logging.getLogger(__name__)

PRICE_DIR = DATA_DIR / "prices"
FIELDS = {"Adj Close": "adj_close", "Close": "close", "Volume": "volume"}


def _download_chunk(tickers: list[str], start: str) -> dict[str, pd.DataFrame]:
    import yfinance as yf

    df = yf.download(tickers, start=start, auto_adjust=False, actions=True, progress=False,
                     threads=True, group_by="column", multi_level_index=True, timeout=30)
    out: dict[str, pd.DataFrame] = {}
    if df is None or df.empty:
        return out
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    for field in list(FIELDS) + ["Stock Splits"]:
        if field not in df.columns.get_level_values(0):
            continue
        sub = df[field]
        if isinstance(sub, pd.Series):
            sub = sub.to_frame(tickers[0])
        out[field] = sub
    return out


def download_all(tickers: list[str], start: str, chunk: int = 40, pause: float = 2.0
                 ) -> tuple[dict[str, pd.DataFrame], pd.DataFrame, list[str]]:
    """Télécharge les cours. Renvoie (tables larges, fractionnements, échecs)."""
    frames: dict[str, list[pd.DataFrame]] = {k: [] for k in FIELDS.values()}
    splits_rows: list[pd.DataFrame] = []
    got: set[str] = set()

    def absorb(res: dict[str, pd.DataFrame]) -> None:
        if "Close" not in res:
            return
        valid = [t for t in res["Close"].columns if res["Close"][t].notna().sum() > 5]
        for src, dst in FIELDS.items():
            if src in res:
                frames[dst].append(res[src][[c for c in valid if c in res[src].columns]])
        if "Stock Splits" in res:
            sp = res["Stock Splits"][[c for c in valid if c in res["Stock Splits"].columns]]
            long = sp.stack().rename("ratio").reset_index()
            long.columns = ["date", "ticker", "ratio"]
            splits_rows.append(long[long["ratio"].fillna(0) > 0])
        got.update(valid)

    batches = [tickers[i:i + chunk] for i in range(0, len(tickers), chunk)]
    for n, batch in enumerate(batches, 1):
        for attempt in range(3):
            try:
                absorb(_download_chunk(batch, start))
                break
            except Exception as exc:  # noqa: BLE001
                wait = pause * (4 ** attempt)
                log.warning("Lot %d/%d : %s ; nouvel essai dans %.0fs", n, len(batches), exc, wait)
                time.sleep(wait)
        time.sleep(pause)

    missing = [t for t in tickers if t not in got]
    # Les titres qui ont déjà échoué (souvent des sociétés retirées de la cote) ne sont
    # retentés individuellement que le lundi, pour ne pas solliciter Yahoo inutilement.
    known_failed = set()
    failed_path = PRICE_DIR / "failed.json"
    if failed_path.exists() and pd.Timestamp.now().weekday() != 0:
        import json
        known_failed = set(json.loads(failed_path.read_text()))
    missing = [t for t in missing if t not in known_failed]
    if missing:
        log.info("Deuxième passage individuel pour %d titres", len(missing))
        for t in missing:
            try:
                absorb(_download_chunk([t], start))
            except Exception as exc:  # noqa: BLE001
                log.debug("%s : %s", t, exc)
            time.sleep(pause / 4)
    failed = [t for t in tickers if t not in got]

    tables = {}
    for name, parts in frames.items():
        if parts:
            tab = pd.concat(parts, axis=1)
            tab = tab.loc[:, ~tab.columns.duplicated()]
            tables[name] = tab.sort_index()
        else:
            tables[name] = pd.DataFrame()
    splits = pd.concat(splits_rows, ignore_index=True) if splits_rows else \
        pd.DataFrame(columns=["date", "ticker", "ratio"])
    return tables, splits, failed


def update_prices(tickers: list[str], start: str, chunk: int, pause: float) -> dict:
    PRICE_DIR.mkdir(parents=True, exist_ok=True)
    tables, splits, failed = download_all(tickers, start, chunk, pause)
    old = load_prices(optional=True)
    stale: list[str] = []
    if old is not None:
        for name in FIELDS.values():
            new_tab = tables.get(name, pd.DataFrame())
            keep = [t for t in failed if t in old[name].columns]
            if keep:
                new_tab = pd.concat([new_tab, old[name][keep]], axis=1) if not new_tab.empty \
                    else old[name][keep]
                tables[name] = new_tab
        stale = [t for t in failed if t in old["close"].columns]
        if stale:
            old_splits = old["splits"]
            splits = pd.concat([splits, old_splits[old_splits["ticker"].isin(stale)]],
                               ignore_index=True)
    if tables["close"].empty:
        raise RuntimeError("Aucun cours téléchargé : Yahoo Finance est peut-être indisponible.")
    for name in FIELDS.values():
        tab = tables[name].sort_index()
        tab.columns = [str(c) for c in tab.columns]
        tab.to_parquet(PRICE_DIR / f"{name}.parquet")
    import json
    (PRICE_DIR / "failed.json").write_text(json.dumps(sorted(set(failed) - set(stale))))
    splits["date"] = pd.to_datetime(splits["date"])
    splits.to_parquet(PRICE_DIR / "splits.parquet", index=False)
    return {
        "requested": len(tickers),
        "downloaded": len(tickers) - len(failed),
        "failed": sorted(set(failed) - set(stale)),
        "stale": sorted(stale),
        "last_date": str(tables["close"].index.max().date()),
    }


def load_prices(optional: bool = False) -> dict | None:
    try:
        out = {name: pd.read_parquet(PRICE_DIR / f"{name}.parquet") for name in FIELDS.values()}
        out["splits"] = pd.read_parquet(PRICE_DIR / "splits.parquet")
    except FileNotFoundError:
        if optional:
            return None
        raise
    for name in FIELDS.values():
        out[name].index = pd.to_datetime(out[name].index)
    return out


def split_factor_after(splits: pd.DataFrame, ticker: str, when: pd.Timestamp) -> float:
    """Produit des ratios de fractionnement postérieurs à `when` (base des cours Yahoo)."""
    s = splits[(splits["ticker"] == ticker) & (splits["date"] > when)]
    return float(np.prod(s["ratio"].values)) if len(s) else 1.0
