"""Rachats nets, contrôle du nombre d'actions, durée minimale de détention, Waters."""
import numpy as np
import pandas as pd

from screener import config
from screener import features as FT
from screener import fundamentals as FD
from screener.portfolio import max_per_sector, review_decision
from tests.conftest import fact


def day(s: str) -> int:
    return int(np.datetime64(s, "D").astype(np.int64))


def hist(rows):
    """rows : (date d'utilisation, actions, date du nombre d'actions, moyenne diluée ?)."""
    u = np.array([day(r[0]) for r in rows], dtype=np.int64)
    sh = np.array([r[1] for r in rows], dtype=float)
    sd = np.array([day(r[2]) for r in rows], dtype=np.int64)
    dil = np.array([r[3] for r in rows], dtype=bool)
    return u, sh, sd, dil


QUARTERS = [("2024-02-10", "2024-02-01"), ("2024-05-10", "2024-05-01"),
            ("2024-08-10", "2024-08-01"), ("2024-11-10", "2024-11-01"),
            ("2025-02-10", "2025-02-01"), ("2025-05-10", "2025-05-01")]


def test_net_issuance_one_year_change():
    h = hist([(u, 100.0 * (0.97 ** k), s, False) for k, (u, s) in enumerate(QUARTERS)])
    v = FT.net_issuance(h, None, day("2025-05-20"))
    assert abs(v - (0.97 ** 4 - 1)) < 1e-12          # mai 2025 contre mai 2024


def test_net_issuance_neutral_to_splits():
    # Fractionnement 2:1 le 2024-09-01 : le nombre publié double, le cours Yahoo est ajusté.
    rows = [(u, 100.0 * (2 if s >= "2024-09-01" else 1), s, False) for u, s in QUARTERS]
    splits = (np.array([day("2024-09-01")]), np.array([2.0]))
    v = FT.net_issuance(hist(rows), splits, day("2025-05-20"))
    assert abs(v) < 1e-12


def test_net_issuance_ignores_spin_offs():
    """Scission (FedEx Freight, 1er juin 2026) : Yahoo l'enregistre comme un fractionnement de
    1,241, mais le nombre d'actions de la société mère ne change pas. Ce n'est pas un rachat."""
    rows = [(u, n * 1e6, s, False) for u, n, s in (
        ("2025-07-18", 236.40, "2025-07-14"), ("2025-09-19", 236.00, "2025-09-15"),
        ("2025-12-19", 235.60, "2025-12-15"), ("2026-03-20", 235.20, "2026-03-16"),
        ("2026-07-21", 234.60, "2026-07-16"), ("2026-09-22", 234.25, "2026-09-17"))]
    spin = (np.array([day("2026-06-01")]), np.array([1.241]))
    v = FT.net_issuance(hist(rows), spin, day("2026-11-06"))
    assert abs(v - (234.25 / 236.00 - 1)) < 1e-12            # -0,74 %, et non -20 %
    v = FT.net_issuance(hist(rows), spin, day("2026-07-25"))  # premier nombre après la scission
    assert abs(v - (234.60 / 236.40 - 1)) < 1e-12


def test_net_issuance_split_already_reflected_before_its_date():
    """Fractionnement 2:1 le 2024-09-01, mais le nombre daté du 2024-08-01, publié après, est
    déjà sur la nouvelle base (moyenne diluée corrigée rétroactivement) : le saut est constaté
    un rapport plus tôt que la date, et la variation reste nulle à toutes les dates."""
    quarters = [("2023-05-10", "2023-05-01"), ("2023-08-10", "2023-08-01"),
                ("2023-11-10", "2023-11-01")] + QUARTERS + \
        [("2025-08-10", "2025-08-01"), ("2025-11-10", "2025-11-01")]
    quarters[5] = ("2024-09-10", "2024-08-01")              # publié après le fractionnement
    rows = [(u, 100.0 * (2 if s >= "2024-08-01" else 1), s, True) for u, s in quarters]
    splits = (np.array([day("2024-09-01")]), np.array([2.0]))
    for d in ("2024-08-20", "2024-09-20", "2024-11-20", "2025-05-20", "2025-08-20", "2025-11-20"):
        assert abs(FT.net_issuance(hist(rows), splits, day(d))) < 1e-12, d


def test_net_issuance_split_and_spin_off_in_the_same_year():
    """Un vrai fractionnement 2:1 et une scission la même année : seul le premier compte."""
    rows = [(u, 100.0 * (2 if s >= "2024-09-01" else 1) * (0.99 ** k), s, False)
            for k, (u, s) in enumerate(QUARTERS)]
    splits = (np.array([day("2024-09-01"), day("2025-01-15")]), np.array([2.0 * 1.3, 1.3]))
    v = FT.net_issuance(hist(rows), splits, day("2025-05-20"))
    assert abs(v - (0.99 ** 4 - 1)) < 1e-12
    # Les deux le même trimestre : le saut publié (x2) désigne le fractionnement, pas la scission
    same = (np.array([day("2024-09-01"), day("2024-10-01")]), np.array([2.0 * 1.3, 1.3]))
    assert abs(FT.net_issuance(hist(rows), same, day("2025-05-20")) - (0.99 ** 4 - 1)) < 1e-12


def test_net_issuance_reverse_split_and_future_split():
    # Regroupement 1 pour 8 le 2024-09-01 : le nombre publié est divisé par 8
    rows = [(u, 800.0 / (8 if s >= "2024-09-01" else 1), s, False) for u, s in QUARTERS]
    reverse = (np.array([day("2024-09-01")]), np.array([0.125]))
    assert abs(FT.net_issuance(hist(rows), reverse, day("2025-05-20"))) < 1e-12
    # Fractionnement postérieur à la date de calcul : sans effet sur les nombres déjà publiés
    flat = [(u, 100.0, s, False) for u, s in QUARTERS]
    later = (np.array([day("2025-06-15")]), np.array([4.0]))
    assert abs(FT.net_issuance(hist(flat), later, day("2025-05-20"))) < 1e-12


def test_net_issuance_keeps_real_issuance_without_split():
    # Émission de 30 % d'actions (acquisition payée en titres), aucun fractionnement listé
    rows = [(u, 100.0 * (1.3 if k >= 3 else 1), s, False) for k, (u, s) in enumerate(QUARTERS)]
    assert abs(FT.net_issuance(hist(rows), None, day("2025-05-20")) - 0.3) < 1e-12
    # Même émission l'année d'une scission (ratio 1,2 un autre trimestre) : elle reste visible
    spin = (np.array([day("2025-03-01")]), np.array([1.2]))
    assert abs(FT.net_issuance(hist(rows), spin, day("2025-05-20")) - 0.3) < 1e-12
    # Petite scission (ratio 1,02) juste après un trimestre où le nombre d'actions a monté de
    # 1,5 % : cette hausse n'est pas prise pour un fractionnement déjà reflété
    rows = [(u, 100.0 * (1.015 if k >= 5 else 1), s, False) for k, (u, s) in enumerate(QUARTERS)]
    small = (np.array([day("2025-05-15")]), np.array([1.02]))
    assert abs(FT.net_issuance(hist(rows), small, day("2025-05-20")) - 0.015) < 1e-12


def test_net_issuance_needs_same_source_and_plausible_ratio():
    rows = [(u, 100.0, s, k >= 4) for k, (u, s) in enumerate(QUARTERS)]   # source changée
    assert np.isnan(FT.net_issuance(hist(rows), None, day("2025-05-20")))
    rows = [(u, 100.0 * (1000 if k >= 4 else 1), s, False) for k, (u, s) in enumerate(QUARTERS)]
    assert np.isnan(FT.net_issuance(hist(rows), None, day("2025-05-20")))   # erreur x1000
    assert np.isnan(FT.net_issuance(None, None, day("2025-05-20")))


def test_shares_suspect():
    ok = hist([(u, 100.0, s, False) for u, s in QUARTERS])
    d = day("2025-05-20")
    assert not FT.shares_suspect(ok, None, d, 1e10, 1e8)        # rotation 1 % par jour
    assert FT.shares_suspect(ok, None, d, 1e13, 1e8)            # 0,001 % : actions x1000
    assert FT.shares_suspect(ok, None, d, 1e8, 1e8)             # 100 % : actions trop basses
    jump = hist([(u, 100.0 * (1000 if k >= 5 else 1), s, False)
                 for k, (u, s) in enumerate(QUARTERS)])
    assert FT.shares_suspect(jump, None, d, np.nan, np.nan)     # saut par rapport au passé


def test_waters_diluted_scale_error_is_ignored(concepts):
    """Moyenne diluée publiée 1000 fois trop grande : la page de garde est gardée."""
    rows = []
    for y in (2024, 2025):
        for q, (s, e, f) in enumerate([("01-01", "03-31", "05-05"), ("04-01", "06-30", "08-05"),
                                       ("07-01", "09-30", "11-05")]):
            filed = f"{y}-{f}"
            rows.append(fact("assets", "Assets", None, f"{y}-{e}", 1000, filed))
            rows.append(fact("revenue", "Revenues", f"{y}-{s}", f"{y}-{e}", 100, filed))
            rows.append(fact("shares_outstanding", "EntityCommonStockSharesOutstanding", None,
                             f"{y}-{e}", 98e6, filed, unit="shares"))
            dil = 98e9 if y == 2025 else 98.5e6
            rows.append(fact("diluted_shares", "WeightedAverageNumberOfDilutedSharesOutstanding",
                             f"{y}-{s}", f"{y}-{e}", dil, filed, unit="shares"))
    comp = FD.Company(pd.DataFrame(rows), concepts)
    st = comp.state(np.datetime64("2025-11-10", "D"))
    assert st["shares"] == 98e6
    assert "nombre dilué incohérent" in st["flags"]
    assert FT.DILUTED_FLAG not in st["flags"]       # ne doit pas passer pour une moyenne diluée


def params(**kw):
    return {**config.portfolio_params(config.settings(), {}, "v1p"), **kw}


def scores(n=200):
    sectors = ["A", "B", "C", "D", "E", "F", "G", "H"]
    idx = [f"S{i:03d}" for i in range(n)]
    return pd.DataFrame({"eligible": True, "rank": range(1, n + 1),
                         "sector": [sectors[i % 8] for i in range(n)]}, index=idx)


def test_v1p_rules():
    p = params()
    assert max_per_sector(p) == 3 and p["min_hold_days"] == 175 and p["hard_exit_mult"] == 3
    assert max_per_sector({**p, "n_positions": 15}) == 2
    assert max_per_sector({**p, "n_positions": 30}) == 4
    other = config.portfolio_params(config.settings(), {}, "v3")
    assert max_per_sector(other) == 5 and other["min_hold_days"] == 0


def test_min_hold_keeps_young_lines_unless_far_down():
    s = scores()
    held = {"S079": 0, "S179": 0, "S089": 0}         # rangs 80, 180 et 90
    entries = {"S079": pd.Timestamp("2026-08-18"), "S179": pd.Timestamp("2026-08-18"),
               "S089": pd.Timestamp("2026-03-17")}
    d = review_decision(s, held, params(), 1, entries, pd.Timestamp("2026-11-16"))
    assert "S079" in d.keep                          # 3 mois : protégée (rang 80 <= 150)
    assert "S179" in d.sell and "150" in d.sell_reasons["S179"]
    assert "S089" in d.sell and "top 50" in d.sell_reasons["S089"]   # 8 mois : règle normale
    # Sans dates d'entrée, la règle habituelle s'applique
    d = review_decision(s, held, params(), 1)
    assert "S079" in d.sell


def test_v1p_sector_cap_on_buys():
    s = scores()
    s["sector"] = ["A"] * 10 + [x for _ in range(24) for x in "BCDEFGHI"][:190]
    d = review_decision(s, {}, params(), 0)
    assert len(d.target) == 20
    assert sum(s.loc[d.target, "sector"] == "A") == 3
