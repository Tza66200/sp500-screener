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
              "audit.json", "changes.json", "classement.csv", "classement.xlsx"):
        assert (run_dir / f).exists(), f


def test_ranking_consistency(run_dir):
    r = load(run_dir, "ranking.json")["rows"]
    for m in ("v1", "v2", "v3"):
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
    assert set(p["models"]) == {"v1", "v2", "v3"}
    for m in ("v1", "v2", "v3"):
        h = p["models"][m]["holdings"]
        assert len(h) == 20
        sectors = pd.Series([x["sector"] for x in h]).value_counts()
        assert sectors.max() <= 5
        assert abs(sum(x["weight"] for x in h) - 1) < 0.02


def test_holdout_hidden(run_dir):
    b = load(run_dir, "backtest.json")
    assert b["revealed"] is False
    assert max(c["date"] for c in b["curves"]) <= "2020-12-31"
    for m in ("v1", "v2", "v3"):
        pm = b["per_model"][m]
        assert "holdout" not in pm["metrics"]["reference"]
        assert {c["id"] for c in pm["criteria"]} == {
            "excess_vs_equal_weight_each_subperiod", "factor_ic_12m_positive",
            "robustness_same_sign", "top20_beats_base_rate_12m"}
        s12 = next(x for x in pm["success"] if x["horizon"] == 12)
        assert 0 < s12["base_rate"] < 1 and len(s12["quintiles"]) == 5
    f = load(run_dir, "factors.json")
    assert f["end_limit"] <= "2020-12-31"
    assert {"composite_v1", "composite_v2", "composite_v3"} <= {x["factor"] for x in f["summary"]}


def test_audit_counts_former_members(run_dir):
    a = load(run_dir, "audit.json")["backtest_universe"]
    assert a["former_members"] == 5          # T45-T49 ont quitté l'indice en 2015
    assert a["former_quotes_ended"] == 5
