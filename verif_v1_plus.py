"""Vérification ponctuelle (branche temporaire) de V1+ dans le pipeline du site.

1. Le backtest de V1+ produit par le pipeline (site/data) doit être identique à celui que
   donne, sur les mêmes données, le code indépendant de l'analyse des corrections
   (analyse_ameliorations.py : rachats nets, risque au sein du secteur et contrôle des
   actions recalculés à part).
2. Contrôles des données : Exxon (deux CIK réunis), Waters (nombre d'actions), titres signalés.
3. Mesure de V1+ en 3 tranches sur les données corrigées, pour la note du site.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyse_ameliorations as A  # noqa: E402
from screener import backtest as B  # noqa: E402
from screener import config as C  # noqa: E402
from screener import features as FT  # noqa: E402
from screener import pipeline as PL  # noqa: E402
from screener import prices as P  # noqa: E402
from screener.portfolio import review_dates  # noqa: E402

log = logging.getLogger("verif")
SITE = Path(os.environ["SCREENER_SITE_DATA_DIR"])
OUT = Path(os.environ.get("VERIF_OUT", "verif"))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    OUT.mkdir(parents=True, exist_ok=True)
    rep: dict = {}
    settings, protocol, concepts = C.settings(), C.protocol(), C.concepts()
    vetoes = C.vetoes()
    preds = C.predecessors()
    rep["faits_en_cache"] = {str(c): (C.DATA_DIR / "sec" / "facts" / f"{c}.parquet").exists()
                             for k, v in preds.items() for c in [k, *v]}
    data = PL.collect(settings, concepts, offline=True)
    info, current, history = data["info"], data["current"], data["history"]
    states = PL.build_states(info, concepts)
    prices = P.load_prices()
    PL.drop_reused_tickers(info, prices, history)
    earn = {float(c): PL.merged_earnings_dates(c, preds) for c in info["cik"].dropna().unique()}
    ctx = FT.Context(prices=prices, states=states, info=info, history=history, current=current,
                     excluded_sectors=settings["universe"]["excluded_sectors"], earnings=earn,
                     market=settings["backtest"]["benchmarks"]["equal_weight"])
    cal = ctx.calendar
    today = cal[-1]

    # Exxon : états avant et après la réorganisation du 1er juillet 2026
    xom = info.at["XOM", "cik"] if "XOM" in info.index else None
    st = states[states["cik"] == float(xom)] if xom is not None else states.iloc[:0]
    rep["exxon"] = {"cik": None if xom is None else int(xom), "etats": int(len(st)),
                    "premier": str(st["known_date"].min().date()) if len(st) else None,
                    "dernier": str(st["known_date"].max().date()) if len(st) else None,
                    "ca_12_mois_dernier": float(st["revenue_ttm"].dropna().iloc[-1])
                    if st["revenue_ttm"].notna().any() else None}

    # Panneau indépendant (code de l'analyse) aux dates de revue du site
    pf = settings["portfolio"]
    day = pf["review_day"]
    bt_start = pd.Timestamp(settings["backtest"]["start"])
    rev_months = sorted({m for m in pf["review_months"]} |
                        {m for v in protocol.get("robustness", {}).values()
                         for m in v.get("review_months", [])})
    official = sorted(set(PL.month_ends(cal, bt_start)) |
                      set(review_dates(cal[:-1], rev_months, day, bt_start)))
    sleeves_all = review_dates(cal[:-1], list(range(1, 13)), day, bt_start)
    dates = sorted(set(official) | set(sleeves_all))
    ex = A.Extras(ctx, settings)
    panel = {}
    for k, d in enumerate(dates):
        panel[d] = A.panel_frame(ctx, d, settings, vetoes, ex)
        if k % 100 == 0:
            log.info("Panneau indépendant : %d/%d", k + 1, len(dates))
    min_elig = settings["backtest"]["min_eligible"]
    valid_start = next(d for d in official if int(panel[d]["eligible_base"].sum()) >= min_elig)
    params = C.portfolio_params(settings, {}, "v1p")
    w = {"momentum": 0.25, "quality": 0.20, "value_chk": 0.15, "buyback": 0.25, "risk_sec": 0.15}
    s = A.Strategy("v1p", "v1", "V1+", "corrige", tuple(w.items()), n_positions=20, hold_rank=50,
                   max_sector=3, min_hold_days=175)
    adj = prices["adj_close"].ffill()
    rf_sym = settings["backtest"]["risk_free"]
    rf_daily = (prices["close"][rf_sym].ffill() / 100 / 252) if rf_sym in prices["close"] \
        else pd.Series(0.0, index=cal)
    mk = A.Market(adj, rf_daily, settings["backtest"]["benchmarks"]["equal_weight"],
                  settings["backtest"]["benchmarks"]["sp500"])
    revs = [r for r in review_dates(cal[:-1], params["review_months"], day, valid_start)
            if r in panel]
    mids = [d for d in sleeves_all if d in panel and d >= valid_start]
    ranks = {d: A.rank_frame(panel[d], s.w, settings["scoring"]["min_factors"])
             for d in sorted(set(revs) | set(mids))}
    sim = A.simulate("v1p:site", mk, ranks, s, params["cost_per_trade"], revs)

    # Comparaison avec le pipeline (courbe hebdomadaire publiée, portefeuille final)
    bt = json.loads((SITE / "backtest.json").read_text())
    pub = pd.Series({pd.Timestamp(r["date"]): r.get("v1p") for r in bt["curves"]}).dropna()
    mine = B.weekly(sim.equity / sim.equity.iloc[0])
    both = pd.concat([pub.rename("pipeline"), mine.rename("analyse")], axis=1).dropna()
    port = json.loads((SITE / "portfolio.json").read_text())["models"]["v1p"]
    held_pub = sorted(h["ticker"] for h in port["holdings"])
    full = bt["per_model"]["v1p"]["metrics"]["reference"].get("full") or {}
    rep["v1p_identique"] = {
        "semaines_comparees": int(len(both)),
        "ecart_relatif_max": float((both["pipeline"] / both["analyse"] - 1).abs().max()),
        "ventes_pipeline": full.get("positions_closed"),
        "ventes_analyse": int(len([p for p in sim.positions
                                   if pd.Timestamp(full.get("start", "1900-01-01")) <= p["exit"]])),
        "portefeuille_identique": held_pub == sorted(sim.holdings),
        "portefeuille_pipeline": held_pub, "portefeuille_analyse": sorted(sim.holdings),
    }
    log.info("V1+ pipeline contre analyse : %s", rep["v1p_identique"])

    # V1+ en 3 tranches sur les données corrigées (note du site)
    sleeve_revs = [[r for r in review_dates(cal[:-1], months, day, valid_start) if r in panel]
                   for months in A.SLEEVES]
    tr = A.run_tranches("v1p:tranches", mk, ranks, s, params["cost_per_trade"], sleeve_revs)
    bench = {k: adj[v] for k, v in settings["backtest"]["benchmarks"].items() if v in adj}
    met = A.measure(tr, mk, bench, rf_daily, tr.all_invested,
                    os.environ.get("VERIF_FIN") or None)
    rep["v1p_tranches"] = {k: met.get(k) for k in ("start", "end", "cagr", "max_drawdown",
                                                   "volatility", "bench_cagr_sp500",
                                                   "bench_cagr_equal_weight", "part_3ans_sp")}
    log.info("V1+ en tranches : %s", rep["v1p_tranches"])

    # Classement du jour : Exxon, Waters, titres signalés
    rk = json.loads((SITE / "ranking.json").read_text())["rows"]
    pick = {x["ticker"]: x for x in rk}
    for t in ("XOM", "WAT"):
        x = pick.get(t) or {}
        rep[t] = {"eligible_v1p": (x.get("models") or {}).get("v1p", {}).get("eligible"),
                  "rang_v1p": (x.get("models") or {}).get("v1p", {}).get("rank"),
                  "rang_v3": (x.get("models") or {}).get("v3", {}).get("rank"),
                  "facteurs": x.get("factors"), "capitalisation": (x.get("extra") or {}).get(
                      "market_cap"), "rachats_nets": (x.get("metrics") or {}).get("net_iss"),
                  "signalements": x.get("flags")}
    rep["signales_aujourdhui"] = sorted(x["ticker"] for x in rk
                                        if "Nombre d'actions incohérent" in (x.get("flags") or ""))
    rep["v1p_portefeuille"] = [{k: h.get(k) for k in ("ticker", "sector", "entry_date", "rank",
                                                      "action", "sell_reason", "return")}
                               for h in port["holdings"]]
    rep["v1p_achats"] = port["hypothetical_buys"]
    (OUT / "verification.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1,
                                                      default=str), encoding="utf-8")
    log.info("Terminé")


if __name__ == "__main__":
    main()
