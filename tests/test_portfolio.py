import pandas as pd

from screener import config
from screener.pipeline import exit_dates
from screener.portfolio import next_review, review_dates, review_decision


def scores(n=60):
    sectors = ["A", "B", "C", "D", "E"]
    idx = [f"S{i:02d}" for i in range(n)]
    return pd.DataFrame({"eligible": True, "rank": range(1, n + 1),
                         "sector": [sectors[i % 5] for i in range(n)]}, index=idx)


def params(**kw):
    return config.portfolio_params(config.settings(), kw)


def test_initial_buy_respects_sector_cap():
    s = scores()
    s["sector"] = ["A"] * 10 + ["B", "C", "D", "E", "F"] * 10
    d = review_decision(s, {}, params(), 0)
    assert len(d.target) == 20
    assert sum(s.loc[d.target, "sector"] == "A") == 5


def test_band_keeps_until_rank_50():
    s = scores()
    held = {"S30": 0, "S55": 0}          # rangs 31 et 56
    d = review_decision(s, held, params(), 1)
    assert "S30" in d.keep
    assert "S55" in d.sell and "top 50" in d.sell_reasons["S55"]
    assert len(d.target) == 20


def test_ineligible_holding_is_sold():
    s = scores()
    s.loc["S01", "eligible"] = False
    d = review_decision(s, {"S01": 0}, params(), 1)
    assert d.sell == ["S01"]


def test_fixed_12m_holding():
    s = scores()
    p = params(holding="fixed_12m")
    d = review_decision(s, {"S40": 2}, p, 4)      # acheté il y a 2 revues : on garde
    assert "S40" in d.keep
    d = review_decision(s, {"S40": 0}, p, 4)      # 4 revues : détention échue, rang 41
    assert "S40" in d.sell


def test_review_dates_and_next_review():
    cal = pd.bdate_range("2024-01-01", "2024-12-31")
    r = review_dates(cal, [3, 5, 8, 11], 15, pd.Timestamp("2024-01-01"))
    assert [d.strftime("%m-%d") for d in r] == ["03-15", "05-15", "08-15", "11-15"]
    cal2 = pd.bdate_range("2025-03-01", "2025-03-31")
    assert review_dates(cal2, [3], 15, pd.Timestamp("2025-01-01"))[0] == pd.Timestamp("2025-03-17")
    assert next_review(pd.Timestamp("2026-10-16"), [3, 5, 8, 11], 15) == pd.Timestamp("2026-11-15")


def test_exit_dates():
    h = pd.DataFrame({"date": pd.to_datetime(["2015-01-01", "2016-01-01", "2017-01-01"]),
                      "tickers": [["A", "B"], ["A"], ["A", "B"]]})
    assert exit_dates(h) == {}                       # B est revenu
    h2 = h.iloc[:2]
    assert exit_dates(h2) == {"B": pd.Timestamp("2016-01-01")}
