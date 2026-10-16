import numpy as np
import pandas as pd
import pytest

from screener import fundamentals as F
from tests.conftest import fact, synthetic_company


def d(s):
    return np.datetime64(s, "D")


def test_q4_derived_from_annual_minus_nine_months(concepts):
    facts = synthetic_company()
    q = F.build_quarters(F.first_filed(facts[facts.tag == "Revenues"]))
    q2019 = q[q["end"].dt.year == 2019].sort_values("end")
    assert list(q2019["val"]) == pytest.approx([100, 101, 102, 103])
    q4 = q2019.iloc[-1]
    assert bool(q4["derived"]) is True
    assert q4["avail"] == pd.Timestamp("2020-02-20")   # disponible au dépôt du 10-K


def test_cash_flow_quarters_from_ytd(concepts):
    facts = synthetic_company()
    sub = facts[facts.tag == "NetCashProvidedByUsedInOperatingActivities"]
    q = F.build_quarters(F.first_filed(sub))
    vals = list(q[q["end"].dt.year == 2020].sort_values("end")["val"])
    assert vals == pytest.approx([11, 12, 13, 14])


def test_q4_from_three_quarters_when_no_nine_month_cumul():
    rows = []
    for i, (s, e, filed) in enumerate([("2020-01-01", "2020-03-31", "2020-05-01"),
                                       ("2020-04-01", "2020-06-30", "2020-08-01"),
                                       ("2020-07-01", "2020-09-30", "2020-11-01")]):
        rows.append(fact("revenue", "Revenues", s, e, 10 + i, filed))
    rows.append(fact("revenue", "Revenues", "2020-01-01", "2020-12-31", 50, "2021-02-15", "10-K"))
    q = F.build_quarters(F.first_filed(pd.DataFrame(rows)))
    assert list(q["val"]) == pytest.approx([10, 11, 12, 17])
    assert q.iloc[-1]["avail"] == pd.Timestamp("2021-02-15")


def test_ttm_requires_four_contiguous_quarters():
    facts = synthetic_company()
    q = F.build_quarters(F.first_filed(facts[facts.tag == "Revenues"]))
    ttm = F.build_ttm(q)
    row = ttm[ttm["end"] == pd.Timestamp("2020-12-31")].iloc[0]
    assert row["val"] == pytest.approx(sum(110 + i for i in range(4)))
    # Fin 2019 : seulement 4 trimestres 2019 -> un TTM ; pas de TTM avant fin 2019
    assert ttm["end"].min() == pd.Timestamp("2019-12-31")


def test_first_filed_value_kept_despite_restatement():
    facts = synthetic_company()
    restated = fact("revenue", "Revenues", "2019-01-01", "2019-03-31", 999, "2020-05-05")
    facts = pd.concat([facts, pd.DataFrame([restated])], ignore_index=True)
    q = F.build_quarters(F.first_filed(facts[facts.tag == "Revenues"]))
    assert q[q["end"] == pd.Timestamp("2019-03-31")]["val"].iloc[0] == pytest.approx(100)


def test_state_is_point_in_time(concepts):
    comp = F.Company(synthetic_company(), concepts)
    # Le 2021-02-19, le 10-K 2020 n'est pas encore déposé : TTM à fin septembre 2020
    st = comp.state(d("2021-02-19"))
    assert st["quarter_end"] == pd.Timestamp("2020-09-30")
    assert st["revenue_ttm"] == pytest.approx(103 + 110 + 111 + 112)
    # Le 2021-02-20, le 10-K est déposé : TTM à fin décembre 2020
    st = comp.state(d("2021-02-20"))
    assert st["quarter_end"] == pd.Timestamp("2020-12-31")
    assert st["revenue_ttm"] == pytest.approx(sum(110 + i for i in range(4)))
    assert st["revenue_ttm_prev"] == pytest.approx(sum(100 + i for i in range(4)))


def test_quarter_yoy_and_acceleration(concepts):
    comp = F.Company(synthetic_company(), concepts)
    st = comp.state(d("2021-11-06"))
    # T3 2021 = 121+2 = 123,0 vs T3 2020 = 112 ; T2 2021 = 122 vs 111
    assert st["revenue_q_yoy"] == pytest.approx(123 / 112 - 1)
    assert st["revenue_q_yoy_prev"] == pytest.approx(122 / 111 - 1)


def test_debt_assumed_zero_is_flagged(concepts):
    comp = F.Company(synthetic_company(), concepts)
    st = comp.state(d("2021-11-06"))
    assert st["debt"] == 0.0
    assert "supposée nulle" in st["flags"]
    assert st["shares"] == 50


def test_company_states_one_row_per_filing_date(concepts):
    states = F.company_states(synthetic_company(), concepts)
    assert states["known_date"].is_monotonic_increasing
    assert states["known_date"].nunique() == len(states)
    assert pd.Timestamp("2021-02-20") in set(states["known_date"])


def test_tag_switch_is_merged(concepts):
    facts = synthetic_company()
    sw = (facts["tag"] == "Revenues") & (facts["end"] >= pd.Timestamp("2021-01-01"))
    facts.loc[sw, "tag"] = "RevenueFromContractWithCustomerExcludingAssessedTax"
    comp = F.Company(facts, concepts)
    st = comp.state(d("2021-11-06"))
    # TTM à fin septembre 2021 : T4 2020 (ancienne étiquette) + T1-T3 2021 (nouvelle)
    assert st["revenue_ttm"] == pytest.approx(113 + 121 + 122 + 123)
    assert st["revenue_q_yoy"] == pytest.approx(123 / 112 - 1)
    assert st["revenue_tag"] == "RevenueFromContractWithCustomerExcludingAssessedTax"


def test_annual_used_when_a_quarterly_report_is_missing(concepts):
    facts = synthetic_company()
    # Le 10-Q du T3 2021 manque dans les données XBRL (cas réel observé)
    gone = (facts["filed"] == pd.Timestamp("2021-11-05"))
    facts = facts[~gone]
    comp = F.Company(facts, concepts)
    st = comp.state(d("2022-02-21"))
    assert st["quarter_end"] == pd.Timestamp("2021-12-31")
    assert st["revenue_ttm"] == pytest.approx(sum(121 + i for i in range(4)))
    assert st["revenue_ttm_prev"] == pytest.approx(sum(110 + i for i in range(4)))


def test_debt_unknown_when_repayments_exist(concepts):
    facts = synthetic_company()
    extra = pd.DataFrame([fact("debt_flows", "RepaymentsOfLongTermDebt", "2021-01-01",
                               "2021-06-30", 40, "2021-08-05")])
    comp = F.Company(pd.concat([facts, extra], ignore_index=True), concepts)
    st = comp.state(d("2021-11-06"))
    assert st["debt"] is None
    assert "inconnue" in st["flags"]


def test_annual_long_term_debt_carried_forward(concepts):
    facts = synthetic_company()
    extra = pd.DataFrame([fact("debt_total_lt", "LongTermDebt", None, "2020-12-31", 500,
                               "2021-02-20", "10-K")])
    comp = F.Company(pd.concat([facts, extra], ignore_index=True), concepts)
    st = comp.state(d("2021-08-06"))          # bilan au 30/06/2021, dette connue au 31/12/2020
    assert st["debt"] == 500
    assert "dernier montant publié" in st["flags"]
