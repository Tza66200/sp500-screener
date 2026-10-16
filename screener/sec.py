"""Téléchargement des données SEC (EDGAR) : dépôts et faits XBRL.

- submissions : liste des dépôts (dates, formulaires, items des 8-K), code SIC.
- companyfacts : valeurs XBRL déclarées, avec leur date de dépôt (champ `filed`).
Les faits ne sont retéléchargés que si un nouveau 10-K / 10-Q est apparu.
Limite SEC : 10 requêtes par seconde ; on reste en dessous.
"""
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests

from . import http
from .config import DATA_DIR

log = logging.getLogger(__name__)

SUB_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
PERIODIC_FORMS = {"10-K", "10-Q", "10-K/A", "10-Q/A", "10-KT", "10-QT"}
SEC_DIR = DATA_DIR / "sec"
UNITS = {"USD", "shares"}
FACTS_VERSION = 2   # changer cette valeur force le retéléchargement de tous les faits


def wanted_tags(concepts: dict) -> dict[tuple[str, str], str]:
    """(taxonomie, étiquette) -> concept."""
    out = {}
    for concept, spec in concepts.items():
        tax = spec.get("taxonomy", "us-gaap")
        for tag in spec["tags"]:
            out[(tax, tag)] = concept
    return out


def parse_submissions(data: dict) -> tuple[dict, pd.DataFrame]:
    meta = {
        "cik": int(data.get("cik", 0)),
        "name": data.get("name"),
        "sic": pd.to_numeric(data.get("sic"), errors="coerce"),
        "sic_description": data.get("sicDescription"),
        "tickers": ",".join(data.get("tickers") or []),
        "fiscal_year_end": data.get("fiscalYearEnd"),
    }
    recent = (data.get("filings") or {}).get("recent") or {}
    cols = ["accessionNumber", "filingDate", "reportDate", "acceptanceDateTime", "form", "items"]
    n = len(recent.get("accessionNumber", []))
    filings = pd.DataFrame({c: recent.get(c, [None] * n) for c in cols})
    filings["filingDate"] = pd.to_datetime(filings["filingDate"], errors="coerce")
    return meta, filings


def parse_companyfacts(data: dict, tags: dict[tuple[str, str], str]) -> pd.DataFrame:
    rows = []
    facts = data.get("facts") or {}
    for (tax, tag), concept in tags.items():
        node = (facts.get(tax) or {}).get(tag)
        if not node:
            continue
        for unit, entries in (node.get("units") or {}).items():
            if unit not in UNITS:
                continue
            for e in entries:
                form = e.get("form") or ""
                if form not in PERIODIC_FORMS:
                    continue
                rows.append((concept, tag, unit, e.get("start"), e.get("end"), e.get("val"),
                             form, e.get("filed"), e.get("accn")))
    df = pd.DataFrame(rows, columns=["concept", "tag", "unit", "start", "end", "val", "form",
                                     "filed", "accn"])
    for c in ("start", "end", "filed"):
        df[c] = pd.to_datetime(df[c], errors="coerce")
    df["val"] = pd.to_numeric(df["val"], errors="coerce")
    return df.dropna(subset=["end", "val", "filed"])


def tag_inventory(data: dict) -> pd.DataFrame:
    """Inventaire de toutes les étiquettes déclarées (pour diagnostiquer les données manquantes)."""
    rows = []
    for tax, nodes in (data.get("facts") or {}).items():
        for tag, node in nodes.items():
            for unit, entries in (node.get("units") or {}).items():
                per = [e for e in entries if (e.get("form") or "") in PERIODIC_FORMS]
                if not per:
                    continue
                rows.append((tax, tag, unit, len(per), max(e.get("end") or "" for e in per),
                             max(e.get("filed") or "" for e in per)))
    return pd.DataFrame(rows, columns=["taxonomy", "tag", "unit", "n", "last_end", "last_filed"])


def _latest_periodic(filings: pd.DataFrame) -> str | None:
    p = filings[filings["form"].isin(PERIODIC_FORMS)]
    if p.empty:
        return None
    return str(p.sort_values("filingDate")["accessionNumber"].iloc[-1])


def refresh(ciks: list[int], concepts: dict, per_second: float = 8.0, workers: int = 6) -> dict:
    """Met à jour submissions + faits pour la liste de CIK. Renvoie un résumé."""
    (SEC_DIR / "facts").mkdir(parents=True, exist_ok=True)
    (SEC_DIR / "submissions").mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": http.sec_user_agent(), "Accept-Encoding": "gzip, deflate"}
    limiter = http.RateLimiter(per_second)
    tags = wanted_tags(concepts)
    state_path = SEC_DIR / "state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    if state.get("__version__") != FACTS_VERSION:
        state = {"__version__": FACTS_VERSION}
    (SEC_DIR / "tags").mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    summary = {"submissions_ok": 0, "facts_updated": 0, "facts_missing": [], "errors": []}
    metas = []

    def work(cik: int):
        sub = http.get(SUB_URL.format(cik=cik), headers=headers, limiter=limiter,
                       session=session, allow_404=True)
        if sub is None:
            return cik, None, None, "submissions introuvables"
        meta, filings = parse_submissions(sub.json())
        filings.to_parquet(SEC_DIR / "submissions" / f"{cik}.parquet", index=False)
        latest = _latest_periodic(filings)
        facts_path = SEC_DIR / "facts" / f"{cik}.parquet"
        updated = False
        if latest and (state.get(str(cik)) != latest or not facts_path.exists()):
            resp = http.get(FACTS_URL.format(cik=cik), headers=headers, limiter=limiter,
                            session=session, allow_404=True)
            if resp is None:
                return cik, meta, latest, "companyfacts introuvables"
            data = resp.json()
            parse_companyfacts(data, tags).to_parquet(facts_path, index=False)
            tag_inventory(data).to_parquet(SEC_DIR / "tags" / f"{cik}.parquet", index=False)
            updated = True
        return cik, meta, latest, "updated" if updated else "unchanged"

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(work, c): c for c in ciks}
        for fut in as_completed(futures):
            cik = futures[fut]
            try:
                cik, meta, latest, status = fut.result()
            except Exception as exc:  # noqa: BLE001
                summary["errors"].append(f"{cik}: {exc}")
                continue
            if meta is not None:
                summary["submissions_ok"] += 1
                metas.append(meta)
            if status == "updated":
                summary["facts_updated"] += 1
                state[str(cik)] = latest
            elif status in ("companyfacts introuvables",):
                summary["facts_missing"].append(cik)
            elif status == "submissions introuvables":
                summary["errors"].append(f"{cik}: {status}")
    state_path.write_text(json.dumps(state))
    if metas:
        new_meta = pd.DataFrame(metas)
        meta_path = SEC_DIR / "companies.parquet"
        if meta_path.exists():
            old = pd.read_parquet(meta_path)
            new_meta = pd.concat([old[~old["cik"].isin(new_meta["cik"])], new_meta])
        new_meta.to_parquet(meta_path, index=False)
    return summary


def load_facts(cik: int) -> pd.DataFrame | None:
    p = SEC_DIR / "facts" / f"{cik}.parquet"
    return pd.read_parquet(p) if p.exists() else None


def load_tags(cik: int) -> pd.DataFrame | None:
    p = SEC_DIR / "tags" / f"{cik}.parquet"
    return pd.read_parquet(p) if p.exists() else None


def load_filings(cik: int) -> pd.DataFrame | None:
    p = SEC_DIR / "submissions" / f"{cik}.parquet"
    return pd.read_parquet(p) if p.exists() else None


def load_companies() -> pd.DataFrame:
    p = SEC_DIR / "companies.parquet"
    return pd.read_parquet(p) if p.exists() else pd.DataFrame(columns=["cik", "sic"])
