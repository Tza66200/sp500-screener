"""Jeu de données FICTIF pour tester la chaîne complète sans réseau.

Ces données ne servent qu'aux tests automatisés : elles ne sont jamais publiées.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

SECTORS = ["Information Technology", "Industrials", "Health Care", "Consumer Discretionary",
           "Consumer Staples", "Financials"]


def build(root: Path, n: int = 60, seed: int = 7, end: str = "2026-10-15") -> None:
    rng = np.random.default_rng(seed)
    (root / "prices").mkdir(parents=True, exist_ok=True)
    (root / "sec" / "facts").mkdir(parents=True, exist_ok=True)
    (root / "sec" / "submissions").mkdir(parents=True, exist_ok=True)
    tickers = [f"T{i:02d}" for i in range(n)]
    cal = pd.bdate_range("2009-06-01", end)

    # Cours : marche aléatoire avec dérive propre à chaque titre
    drift = rng.normal(0.0003, 0.0003, n)
    rets = rng.normal(drift, 0.018, size=(len(cal), n))
    close = 50 * np.exp(np.cumsum(rets, axis=0))
    adj = pd.DataFrame(close, index=cal, columns=tickers)
    for b, mu in (("^SP500TR", 0.0004), ("RSP", 0.00035)):
        adj[b] = 1000 * np.exp(np.cumsum(rng.normal(mu, 0.011, len(cal))))
    adj["^IRX"] = 2.0
    adj.loc[adj.index < "2015-01-02", "T50":"T54"] = np.nan    # entrées plus tardives
    adj.loc[adj.index > "2019-06-28", "T45":"T49"] = np.nan    # cotations arrêtées
    vol = pd.DataFrame(1e6, index=cal, columns=adj.columns).where(adj.notna())
    adj.to_parquet(root / "prices" / "adj_close.parquet")
    adj.to_parquet(root / "prices" / "close.parquet")
    vol.to_parquet(root / "prices" / "volume.parquet")
    pd.DataFrame({"date": pd.to_datetime([]), "ticker": [], "ratio": []}).to_parquet(
        root / "prices" / "splits.parquet", index=False)

    # Composition
    first = tickers[:50]
    mid = tickers[:45] + tickers[50:55]
    last = tickers[:45] + tickers[50:60]
    hist = pd.DataFrame({"date": pd.to_datetime(["2009-01-02", "2015-01-02", "2020-01-02"]),
                         "tickers": [",".join(first), ",".join(mid), ",".join(last)]})
    hist.to_parquet(root / "membership_history.parquet", index=False)
    cur = pd.DataFrame({"ticker": last, "name": [f"Société {t}" for t in last],
                        "sector": [SECTORS[int(t[1:]) % 6] for t in last],
                        "sub_industry": "Test", "cik": [int(t[1:]) + 1 for t in last],
                        "date_added": "", "source": "test"})
    cur.to_parquet(root / "current_constituents.parquet", index=False)
    info = pd.DataFrame({"ticker": tickers, "name": [f"Société {t}" for t in tickers],
                         "sector": [SECTORS[i % 6] for i in range(n)], "sub_industry": "Test",
                         "cik": [float(i + 1) for i in range(n)],
                         "current_member": [t in last for t in tickers],
                         "sector_source": "GICS"})
    info.to_parquet(root / "ticker_info.parquet", index=False)
    pd.DataFrame({"cik": range(1, n + 1), "sic": 3570}).to_parquet(
        root / "sec" / "companies.parquet", index=False)
    (root / "collect_status.json").write_text(json.dumps({
        "warnings": [], "constituents_source": "test", "history_last_date": "2020-01-02",
        "sec_refreshed_at": "2026-10-15T23:00:00+00:00"}))

    # Faits SEC trimestriels
    for i in range(n):
        cik = i + 1
        rows = []
        g = rng.normal(0.02, 0.03)
        rev = 1000.0 * (1 + i / 20)
        margin = rng.uniform(0.05, 0.3)
        for y in range(2009, 2027):
            ytd = {"rev": 0.0, "cfo": 0.0, "capex": 0.0}
            for q in range(4):
                qend = pd.Timestamp(year=y, month=3 * (q + 1), day=1) + pd.offsets.MonthEnd(0)
                qstart = pd.Timestamp(year=y, month=3 * q + 1, day=1)
                if qend > pd.Timestamp(end) - pd.Timedelta(days=40):
                    break
                rev *= 1 + g + rng.normal(0, 0.02)
                cfo = rev * margin * rng.uniform(0.8, 1.2)
                capex = rev * 0.05
                ytd["rev"] += rev
                ytd["cfo"] += cfo
                ytd["capex"] += capex
                annual = q == 3
                filed = qend + pd.Timedelta(days=55 if annual else 35)
                form = "10-K" if annual else "10-Q"

                def add(concept, tag, start, val, unit="USD"):
                    rows.append({"concept": concept, "tag": tag, "unit": unit, "start": start,
                                 "end": qend, "val": float(val), "form": form, "filed": filed,
                                 "accn": f"{cik}-{qend.date()}"})
                if annual:
                    add("revenue", "Revenues", pd.Timestamp(year=y, month=1, day=1), ytd["rev"])
                else:
                    add("revenue", "Revenues", qstart, rev)
                    add("operating_income", "OperatingIncomeLoss", qstart, rev * margin)
                    add("net_income", "NetIncomeLoss", qstart, rev * margin * 0.75)
                    add("dna", "DepreciationDepletionAndAmortization", qstart, rev * 0.03)
                    add("gross_profit", "GrossProfit", qstart, rev * 0.45)
                ystart = pd.Timestamp(year=y, month=1, day=1)
                add("cfo", "NetCashProvidedByUsedInOperatingActivities", ystart, ytd["cfo"])
                add("capex", "PaymentsToAcquirePropertyPlantAndEquipment", ystart, ytd["capex"])
                add("assets", "Assets", pd.NaT, rev * 8)
                add("cash", "CashAndCashEquivalentsAtCarryingValue", pd.NaT, rev * 0.5)
                add("debt_total_lt", "LongTermDebt", pd.NaT, rev * rng.uniform(0, 3))
                add("shares_outstanding", "EntityCommonStockSharesOutstanding", pd.NaT,
                    1e3 * (1 + i), unit="shares")
                if annual:
                    # Compte de résultat annuel (T4 déduit = annuel - 9 mois)
                    for concept, tag, frac in (("operating_income", "OperatingIncomeLoss", margin),
                                               ("net_income", "NetIncomeLoss", margin * 0.75),
                                               ("dna", "DepreciationDepletionAndAmortization", 0.03),
                                               ("gross_profit", "GrossProfit", 0.45)):
                        add(concept, tag, ystart, ytd["rev"] * frac)
        df = pd.DataFrame(rows)
        df["start"] = pd.to_datetime(df["start"])
        df.to_parquet(root / "sec" / "facts" / f"{cik}.parquet", index=False)
        filings = pd.DataFrame({
            "accessionNumber": [f"{cik}-er-{k}" for k in range(8)],
            "filingDate": pd.to_datetime([f"{y}-{m:02d}-25" for y in (2025, 2026)
                                          for m in (1, 4, 7, 10)]),
            "reportDate": None, "acceptanceDateTime": None, "form": "8-K", "items": "2.02,9.01"})
        if cik == 3:   # société fictive visée par une offre de rachat
            filings = pd.concat([filings, pd.DataFrame({
                "accessionNumber": ["m1"], "filingDate": pd.to_datetime(["2026-09-01"]),
                "reportDate": None, "acceptanceDateTime": None, "form": ["DEFM14A"],
                "items": [""]})], ignore_index=True)
        filings.to_parquet(root / "sec" / "submissions" / f"{cik}.parquet", index=False)
