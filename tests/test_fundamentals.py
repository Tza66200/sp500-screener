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


def test_material_interest_means_debt_unknown(concepts):
    facts = synthetic_company()
    rows = []
    for y, filed in ((2020, "2021-02-20"), (2021, "2022-02-20")):
        rows.append(fact("interest_expense", "InterestExpense", f"{y}-01-01", f"{y}-12-31", 30,
                         filed, "10-K"))
    comp = F.Company(pd.concat([facts, pd.DataFrame(rows)], ignore_index=True), concepts)
    st = comp.state(d("2022-02-21"))      # 30 d'intérêts pour ~1 033 d'actifs
    assert st["debt"] is None


def test_divestiture_restatement_dollar_tree_case(concepts):
    """Cession d'une activité : l'exercice est republié sans elle, mais les 9 premiers mois
    l'incluaient encore. Avant correction, le T4 reconstitué était négatif et la croissance
    absurde."""
    rows = []
    for y in (2020, 2021):
        for qi, (s, e, filed) in enumerate([("01-01", "03-31", "05-05"), ("04-01", "06-30", "08-05"),
                                            ("07-01", "09-30", "11-05")]):
            rows.append(fact("revenue", "Revenues", f"{y}-{s}", f"{y}-{e}", 100, f"{y}-{filed}"))
        rows.append(fact("revenue", "Revenues", f"{y}-01-01", f"{y}-09-30", 300, f"{y}-11-05"))
    rows.append(fact("revenue", "Revenues", "2020-01-01", "2020-12-31", 400, "2021-02-20", "10-K"))
    # 10-K 2021 : activité cédée retirée, 2020 republié sur la même base
    rows.append(fact("revenue", "Revenues", "2021-01-01", "2021-12-31", 240, "2022-02-20", "10-K"))
    rows.append(fact("revenue", "Revenues", "2020-01-01", "2020-12-31", 240, "2022-02-20", "10-K"))
    # 10-Q T1 2022 : comparatif T1 2021 republié
    rows.append(fact("revenue", "Revenues", "2022-01-01", "2022-03-31", 63, "2022-05-05"))
    rows.append(fact("revenue", "Revenues", "2021-01-01", "2021-03-31", 60, "2022-05-05"))
    comp = F.Company(pd.DataFrame(rows), concepts)
    q = F.build_quarters(F.first_filed(pd.DataFrame(rows)), nonneg=True)
    assert (q["val"] >= 0).all()                          # T4 2021 négatif écarté
    st = comp.state(d("2022-05-06"))
    assert st["revenue_ttm"] == pytest.approx(240)
    assert st["revenue_ttm_prev"] == pytest.approx(240)   # 2020 republié, même base
    # Avant la republication, l'état utilise les chiffres connus alors (pas d'anticipation)
    st0 = comp.state(d("2021-03-01"))
    assert st0["revenue_ttm"] == pytest.approx(400)


def test_sue_standardized_surprise(concepts):
    rows = []
    vals = {}
    k = 0
    for y in range(2018, 2022):
        for qi, (s, e, filed) in enumerate([("01-01", "03-31", "05-05"), ("04-01", "06-30", "08-05"),
                                            ("07-01", "09-30", "11-05"), ("10-01", "12-31", "02-20")]):
            v = 10 + k + (k * k) % 7
            vals[(y, qi)] = v
            fy = y + 1 if qi == 3 else y
            rows.append(fact("net_income", "NetIncomeLoss", f"{y}-{s}", f"{y}-{e}", v, f"{fy}-{filed}"))
            k += 1
    comp = F.Company(pd.DataFrame(rows), concepts)
    sue, q = comp.sue(d("2022-03-01"))
    changes = [vals[(y, qi)] - vals[(y - 1, qi)] for y in (2019, 2020, 2021) for qi in range(4)]
    hist = changes[-9:-1]
    expected = changes[-1] / np.std(hist, ddof=1)
    assert q == pd.Timestamp("2021-12-31")
    assert sue == pytest.approx(expected)
