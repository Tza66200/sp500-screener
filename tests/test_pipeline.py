"""Test de bout en bout sur données fictives (sans réseau)."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml

from tests import synthetic

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def run_dir(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("e2e")
    data, site, hist, cfg = tmp / "data", tmp / "site", tmp / "history", tmp / "config"
    synthetic.build(data)
    shutil.copytree(ROOT / "config", cfg)
    s = yaml.safe_load((cfg / "settings.yaml").read_text())
    s["backtest"]["min_eligible"] = 20
    s["scoring"]["min_sector_size"] = 5
    (cfg / "settings.yaml").write_text(yaml.safe_dump(s, allow_unicode=True))
    pr = yaml.safe_load((cfg / "protocol.yaml").read_text())
    pr["success_top_n"] = 5                 # univers fictif de ~40 titres
    pr["holdout"]["revealed"] = False       # vérifie le masquage, quel que soit l'état réel
    (cfg / "protocol.yaml").write_text(yaml.safe_dump(pr, allow_unicode=True))
    env = {**os.environ, "SCREENER_DATA_DIR": str(data), "SCREENER_SITE_DATA_DIR": str(site),
           "SCREENER_HISTORY_DIR": str(hist), "SCREENER_CONFIG_DIR": str(cfg)}
    proc = subprocess.run([sys.executable, "-m", "screener.pipeline", "run", "--offline"],
                          cwd=ROOT, env=env, capture_output=True, text=True, timeout=900)
    assert proc.returncode == 0, proc.stderr[-4000:]
    return site


def load(site, name):
    return json.loads((site / name).read_text())


def test_outputs_exist(run_dir):
    for f in ("meta.json", "ranking.json", "portfolio.json", "backtest.json", "factors.json",
              "audit.json", "changes.json", "classement.csv", "classement.xlsx", "ventes.csv"):
        assert (run_dir / f).exists(), f


def test_trades_export(run_dir):
    t = pd.read_csv(run_dir / "ventes.csv", encoding="utf-8-sig")
    assert t["Modèle"].nunique() == 4
    # Période réservée masquée : ni vente après 2020, ni ligne encore détenue
    assert len(t) > 0 and (t["Statut"] == "vendue").all()
    sold_on, bought_on = pd.to_datetime(t["Vente"]), pd.to_datetime(t["Achat"])
    assert (sold_on <= "2020-12-31").all() and (sold_on > bought_on).all()
    assert t["Rendement"].notna().all() and (t["Rendement"] > -1).all()
    assert t["S&P 500 même période"].notna().all()


def test_ranking_consistency(run_dir):
    r = load(run_dir, "ranking.json")["rows"]
    for m in ("v1", "v2", "v3", "v1p"):
        elig = sorted([x for x in r if x["models"][m]["eligible"]],
                      key=lambda x: x["models"][m]["rank"])
        ranks = [x["models"][m]["rank"] for x in elig]
        assert ranks[0] == 1 and ranks == list(range(1, len(ranks) + 1))
        scores = [x["models"][m]["score"] for x in elig]
        assert scores == sorted(scores, reverse=True)
        assert all(0 <= x["models"][m]["score"] <= 100 for x in elig)
    fin = [x for x in r if x["sector"] == "Financials"]
    assert fin and all(not x["models"]["v2"]["eligible"] for x in fin)
    t02 = next(x for x in r if x["ticker"] == "T02")      # CIK 3 : offre de rachat fictive
    assert not t02["models"]["v2"]["eligible"]
    assert any("rachat" in m for m in t02["models"]["v2"]["reasons"])
    assert "earnings" in r[0]["factors"]


def test_portfolio_rules(run_dir):
    p = load(run_dir, "portfolio.json")
    assert set(p["models"]) == {"v1", "v2", "v3", "v1p"}
    caps = {"v1": 5, "v2": 5, "v3": 5, "v1p": 3}
    n_sectors = 5          # secteurs éligibles de l'univers fictif (financières exclues)
    for m in ("v1", "v2", "v3", "v1p"):
        h = p["models"][m]["holdings"]
        assert len(h) == min(20, caps[m] * n_sectors)
        sectors = pd.Series([x["sector"] for x in h]).value_counts()
        assert sectors.max() <= caps[m]
        assert p["models"][m]["params"]["max_per_sector"] == caps[m]
        assert abs(sum(x["weight"] for x in h) - 1) < 0.02
    assert p["models"]["v1p"]["params"]["min_hold_days"] == 175


def test_holdout_hidden(run_dir):
    b = load(run_dir, "backtest.json")
    assert b["revealed"] is False
    assert max(c["date"] for c in b["curves"]) <= "2020-12-31"
    for m in ("v1", "v2", "v3", "v1p"):
        pm = b["per_model"][m]
        assert "holdout" not in pm["metrics"]["reference"]
        assert {c["id"] for c in pm["criteria"]} == {
            "excess_vs_equal_weight_each_subperiod", "factor_ic_12m_positive",
            "robustness_same_sign", "top20_beats_base_rate_12m"}
        s12 = next(x for x in pm["success"] if x["horizon"] == 12)
        assert 0 < s12["base_rate"] < 1 and len(s12["quintiles"]) == 5
    f = load(run_dir, "factors.json")
    assert f["end_limit"] <= "2020-12-31"
    assert {"composite_v1", "composite_v2", "composite_v3", "composite_v1p", "buyback",
            "risk_sec"} <= {x["factor"] for x in f["summary"]}


def test_audit_counts_former_members(run_dir):
    a = load(run_dir, "audit.json")["backtest_universe"]
    assert a["former_members"] == 5          # T45-T49 ont quitté l'indice en 2015
    assert a["former_quotes_ended"] == 5


def test_incomplete_last_session_is_dropped():
    """Dernière séance sans cours pour tout ou partie des actions (Yahoo, 10 et 11/11/2026) :
    elle est retirée, le classement se fait sur la dernière séance complète."""
    from screener.pipeline import drop_incomplete_sessions

    idx = pd.bdate_range("2026-11-02", periods=7)
    names = [f"S{i:02d}" for i in range(100)]
    full = pd.DataFrame(1.0, index=idx, columns=names + ["^SP500TR"])

    def run(missing, days=1):
        close = full.copy()
        close.loc[idx[-days:], missing] = float("nan")
        prices = {n: close.copy() for n in ("adj_close", "close", "volume")}
        return drop_incomplete_sessions(prices, names + ["ABSENT"]), prices

    dropped, prices = run(names)                 # 10/11 : l'indice seul a un cours
    assert dropped == [idx[-1]]
    assert all(len(t) == 6 and t.index[-1] == idx[-2] for t in prices.values())
    dropped, prices = run(names[55:])            # 11/11 : coupure pendant le téléchargement
    assert dropped == [idx[-1]] and len(prices["close"]) == 6
    dropped, prices = run(names[90:], days=2)    # deux séances incomplètes de suite
    assert dropped == [idx[-1], idx[-2]] and prices["close"].index[-1] == idx[-3]
    dropped, prices = run(names[:1])             # un seul titre sans cours : séance gardée
    assert dropped == [] and len(prices["close"]) == 7


def test_spin_off_is_not_a_buyback(run_dir):
    """T10 : scission fictive enregistrée comme un fractionnement de 1,25 en mars 2026. Ses
    rachats nets restent ceux de ses nombres d'actions publiés (-2 % par an), pas -21,6 %."""
    r = load(run_dir, "ranking.json")["rows"]
    t10 = next(x for x in r if x["ticker"] == "T10")
    assert t10["metrics"]["net_iss"] == pytest.approx(-0.02, abs=1e-6)
    assert t10["extra"]["market_cap"] > 0


def test_v1p_factors_in_ranking(run_dir):
    r = load(run_dir, "ranking.json")["rows"]
    meta = load(run_dir, "meta.json")
    w = meta["models"]["v1p"]["weights"]
    assert w["buyback"] == 0.25 and w["risk_sec"] == 0.15 and w["growth"] == 0
    assert meta["models"]["v1p"]["note"]
    elig = [x for x in r if x["models"]["v1p"]["eligible"]]
    assert elig and all(x["factors"]["buyback"] is not None for x in elig)
    assert all(x["factors"]["risk_sec"] is not None for x in elig)
    # Rachats : sociétés fictives aux nombres d'actions différents d'une année sur l'autre
    assert len({round(x["metrics"]["net_iss"], 6) for x in elig}) > 5
