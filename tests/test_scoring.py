import numpy as np
import pandas as pd
import pytest

from screener import config
from screener import scoring as S
from screener.features import METRICS


def frame(n=30, seed=0, sectors=("Information Technology", "Industrials", "Health Care")):
    rng = np.random.default_rng(seed)
    idx = [f"T{i:02d}" for i in range(n)]
    f = pd.DataFrame(index=pd.Index(idx, name="ticker"))
    f["sector"] = [sectors[i % len(sectors)] for i in range(n)]
    f["cik"] = np.arange(n, dtype=float) + 1
    f["price"] = 100.0
    f["known_date"] = pd.Timestamp("2026-08-01")
    f["fundamentals_age_days"] = 60
    f["dollar_vol_63"] = 1e8
    f["above_sma200"] = True
    for m in METRICS:
        f[m] = rng.normal(size=n)
    return f


def test_percentile_bounds_and_direction():
    s = pd.Series([1.0, 2.0, 3.0, np.nan])
    up = S.percentile(s, True)
    down = S.percentile(s, False)
    assert up.iloc[2] > up.iloc[0]
    assert down.iloc[0] > down.iloc[2]
    assert np.isnan(up.iloc[3])
    assert up.dropna().between(0, 100).all()


def test_sector_relative_ranking_falls_back_for_small_sectors():
    vals = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 100.0])
    sectors = pd.Series(["A"] * 8 + ["B"])
    r = S.ranked(vals, sectors, True, True, min_sector_size=8)
    # Secteur B trop petit : rang calculé sur tout l'univers -> meilleur
    assert r.iloc[8] == pytest.approx((9 - 0.5) / 9 * 100)
    # Secteur A : rang interne
    assert r.iloc[7] == pytest.approx((8 - 0.5) / 8 * 100)


def test_factor_needs_half_of_its_metrics_and_composite_needs_four_factors():
    st = config.settings()
    f = frame()
    f.loc["T00", ["rev_growth", "rev_accel"]] = np.nan          # croissance : 1/3 -> absent
    f.loc["T01", ["rev_growth", "rev_accel", "oi_change_assets"]] = np.nan
    f.loc["T01", ["fcf_yield", "ebit_ev"]] = np.nan              # 2 facteurs absents
    out = S.score(f, st)
    assert np.isnan(out.at["T00", "growth"])
    assert not np.isnan(out.at["T00", "composite_v1"])           # 4 facteurs V1 sur 5
    assert np.isnan(out.at["T01", "composite_v1"])               # 3 facteurs V1 sur 5
    # V2 n'utilise pas la croissance : T01 n'a perdu qu'un de ses facteurs
    assert not np.isnan(out.at["T01", "composite_v2"])


def test_composite_is_weighted_average_for_each_model():
    st = config.settings()
    f = frame()
    out = S.score(f, st)
    row = out.loc["T05"]
    for model in ("v1", "v2"):
        w = config.model_weights(st, model)
        expected = sum(row[k] * v for k, v in w.items() if v > 0)
        assert row[f"composite_{model}"] == pytest.approx(expected)
    assert row["composite"] == row[f"composite_{st['default_model']}"]


def test_excluded_sector_is_not_scored_and_does_not_affect_others():
    st = config.settings()
    f = frame()
    base = S.score(f, st)
    f2 = f.copy()
    f2.loc["T03", "sector"] = "Financials"
    f2.loc["T03", "mom_12_1"] = 1e9
    out = S.score(f2, st)
    assert "sector" in out.at["T03", "reasons"]
    assert np.isnan(out.at["T03", "composite"])
    assert out.drop("T03")["pct_mom_12_1"].max() <= 100


def test_duplicate_share_classes_keep_most_liquid():
    st = config.settings()
    f = frame()
    f.loc["T02", "cik"] = f.at["T01", "cik"]
    f.loc["T02", "dollar_vol_63"] = 2e8
    out = S.score(f, st)
    assert "duplicate" in out.at["T01", "reasons"]
    assert out.at["T02", "reasons"] == []


def test_filters_and_rank():
    st = config.settings()
    f = frame()
    f.loc["T04", "fundamentals_age_days"] = 400
    f.loc["T06", "dollar_vol_63"] = 1e6
    f.loc["T07", "above_sma200"] = False
    out = S.apply_filters(S.score(f, st), st, trend_filter=True,
                          merger={"T08": "DEFM14A du 2026-09-01"}, vetoes={"T09": "test"})
    assert out.at["T04", "reasons"] == ["stale"]
    assert out.at["T06", "reasons"] == ["liquidity"]
    assert out.at["T07", "reasons"] == ["trend"]
    assert out.at["T08", "reasons"] == ["merger"]
    assert out.at["T09", "reasons"] == ["veto"]
    elig = out[out["eligible"]]
    assert len(elig) == 25
    assert out["eligible_v1"].sum() == 25 and out["rank_v1"].min() == 1
    best = elig["composite"].idxmax()
    assert out.at[best, "rank"] == 1
    txt = S.reason_text(["merger"], merger={"T08": "DEFM14A du 2026-09-01"}, ticker="T08")
    assert "DEFM14A" in txt[0]
