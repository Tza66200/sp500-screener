import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from screener import config  # noqa: E402


@pytest.fixture(scope="session")
def concepts():
    return config.concepts()


def fact(concept, tag, start, end, val, filed, form="10-Q", unit="USD", accn=None):
    return {
        "concept": concept, "tag": tag, "unit": unit,
        "start": pd.Timestamp(start) if start else pd.NaT,
        "end": pd.Timestamp(end), "val": float(val), "form": form,
        "filed": pd.Timestamp(filed), "accn": accn or f"{filed}-{form}",
    }


def synthetic_company(years=(2019, 2020, 2021), base_rev=100.0, growth=0.10):
    """Société fictive, exercice = année civile. 10-Q : trimestre (3 mois) pour le compte de
    résultat et cumul depuis janvier pour les flux de trésorerie. 10-K : annuel."""
    rows = []
    q_ends = ["03-31", "06-30", "09-30", "12-31"]
    filed_q = ["05-05", "08-05", "11-05"]
    for k, y in enumerate(years):
        rev_q = [base_rev * (1 + growth) ** k + i for i in range(4)]  # 4 trimestres distincts
        cfo_q = [10.0 + i + k for i in range(4)]
        for qi in range(3):
            end = f"{y}-{q_ends[qi]}"
            qstart = f"{y}-{['01-01', '04-01', '07-01'][qi]}"
            filed = f"{y}-{filed_q[qi]}"
            rows.append(fact("revenue", "Revenues", qstart, end, rev_q[qi], filed))
            rows.append(fact("operating_income", "OperatingIncomeLoss", qstart, end,
                             rev_q[qi] * 0.2, filed))
            rows.append(fact("cfo", "NetCashProvidedByUsedInOperatingActivities", f"{y}-01-01",
                             end, sum(cfo_q[:qi + 1]), filed))
            rows.append(fact("assets", "Assets", None, end, 1000 + 10 * k + qi, filed))
            rows.append(fact("shares_outstanding", "EntityCommonStockSharesOutstanding", None,
                             f"{y}-{['04-20', '07-20', '10-20'][qi]}", 50, filed, unit="shares"))
        # Cumul 9 mois du CA (souvent publié aussi)
        rows.append(fact("revenue", "Revenues", f"{y}-01-01", f"{y}-09-30", sum(rev_q[:3]),
                         f"{y}-11-05"))
        filed_k = f"{y + 1}-02-20"
        rows.append(fact("revenue", "Revenues", f"{y}-01-01", f"{y}-12-31", sum(rev_q), filed_k,
                         form="10-K"))
        rows.append(fact("operating_income", "OperatingIncomeLoss", f"{y}-01-01", f"{y}-12-31",
                         sum(rev_q) * 0.2, filed_k, form="10-K"))
        rows.append(fact("cfo", "NetCashProvidedByUsedInOperatingActivities", f"{y}-01-01",
                         f"{y}-12-31", sum(cfo_q), filed_k, form="10-K"))
        rows.append(fact("assets", "Assets", None, f"{y}-12-31", 1000 + 10 * k + 3, filed_k,
                         form="10-K"))
        rows.append(fact("shares_outstanding", "EntityCommonStockSharesOutstanding", None,
                         f"{y + 1}-02-01", 50, filed_k, form="10-K", unit="shares"))
    return pd.DataFrame(rows)
