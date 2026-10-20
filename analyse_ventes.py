"""Analyse ponctuelle (branche temporaire) : vendre dès que l'étiquette « À vendre » du site
apparaît, au lieu d'attendre la revue trimestrielle.

Le classement est recalculé à chaque séance depuis la première revue, avec le moteur du site
(screener.features, screener.scoring, screener.portfolio), sur les données en cache (lecture
seule, aucun téléchargement). Pour chaque modèle, trois façons de gérer le portefeuille :

- trimestriel : la règle du site (achats, ventes et rééquilibrage aux seules revues) ;
- vente_immediate : en plus, chaque soir, une ligne qui sort du top 50 ou n'est plus
  éligible est vendue à la clôture suivante ; l'argent attend la revue suivante, placé au
  taux des bons du Trésor à 13 semaines ;
- suivi_quotidien : chaque soir, on applique l'étiquette du site, ventes ET remplacements
  (« À acheter »), à la clôture suivante ; rééquilibrage à 5 % aux revues seulement.

Mêmes conventions que le backtest du site : ordres à la clôture de la séance qui suit la
décision, 0,10 % de frais par transaction, dividendes réinvestis, mêmes limites (pas de
filtre d'offre de rachat dans l'historique, sociétés sans cours absentes).

Sorties dans resultats/ : comparaison.json, courbes.csv, annees.csv, operations.csv,
verification.json.
"""
from __future__ import annotations

import bisect
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from screener import backtest as B  # noqa: E402
from screener import config as C  # noqa: E402
from screener import features as FT  # noqa: E402
from screener import pipeline as PL  # noqa: E402
from screener import prices as P  # noqa: E402
from screener import report as R  # noqa: E402
from screener import sec as SEC  # noqa: E402
from screener.portfolio import review_dates, review_decision  # noqa: E402

log = logging.getLogger("analyse")
OUT = Path(os.environ.get("ANALYSE_OUT", "resultats"))
MODES = ("trimestriel", "vente_immediate", "suivi_quotidien")
REBUY_WINDOW = 63          # séances, soit environ trois mois


class Market:
    """Cours ajustés (prolongés, comme dans le backtest du site) et taux sans risque."""

    def __init__(self, adj: pd.DataFrame, rf_daily: pd.Series, ew_symbol: str):
        self.cal = adj.index
        self.cols = {t: j for j, t in enumerate(adj.columns)}
        self.px = adj.values
        ratio = np.ones_like(self.px)
        with np.errstate(invalid="ignore", divide="ignore"):
            ratio[1:] = self.px[1:] / self.px[:-1]
        self.ratio = np.where(np.isfinite(ratio), ratio, 1.0)
        self.rf = rf_daily.reindex(self.cal).ffill().fillna(0.0).to_numpy(dtype=float)
        self.ew = self.cols.get(ew_symbol)

    def price(self, t: str, i: int) -> float:
        return float(self.px[i, self.cols[t]])


def growth(a: float, b: float) -> float | None:
    """b / a - 1, ou None si l'un des cours manque."""
    ok = np.isfinite(a) and np.isfinite(b) and a > 0
    return float(b / a - 1) if ok else None


def closed(mk: Market, t: str, m: dict, i: int, reason: str, kind: str) -> dict:
    """Même calcul que backtest._closed, avec le type de vente en plus."""
    p0, p1 = mk.px[m["entry_pos"], mk.cols[t]], mk.px[i, mk.cols[t]]
    ok = bool(p0) and np.isfinite(p0) and np.isfinite(p1)
    return {"ticker": t, "entry": mk.cal[m["entry_pos"]], "exit": mk.cal[i],
            "return": float(p1 / p0 - 1) if ok else None, "reason": reason, "kind": kind}


def simulate(mode: str, mk: Market, ranks: dict, params: dict, reviews: list,
             model: str) -> B.Result:
    """Simulation quotidienne. En mode « trimestriel », reproduit exactement backtest.run."""
    cal, cols, ratio = mk.cal, mk.cols, mk.ratio
    review_pos = {cal.get_loc(r): r for r in reviews if r in ranks}
    first = min(review_pos)
    daily = mode != "trimestriel"
    check_pos = {cal.get_loc(d) for d in ranks} if daily else set()
    rate = params["cost_per_trade"]
    values: dict[str, float] = {}
    meta: dict[str, dict] = {}
    cash = 1.0
    eq = np.full(len(cal), np.nan)
    cash_w = np.full(len(cal), np.nan)
    npos = np.full(len(cal), np.nan)
    res = B.Result(name=f"{model}:{mode}", params=params, equity=pd.Series(dtype=float))
    res.trades, res.costs = [], []
    pending = None
    review_idx = -1

    def rank_of(scores: pd.DataFrame, t: str):
        if t in scores.index and bool(scores.at[t, "eligible"]):
            return int(scores.at[t, "rank"])
        return None

    def log_trade(i, op, t, decided, scores, reason, kind, weight):
        res.trades.append({"modele": model, "strategie": mode, "decision": decided,
                           "execution": cal[i], "pos": i, "ticker": t, "operation": op,
                           "type": kind, "motif": reason, "rang_a_la_decision": rank_of(scores, t),
                           "poids": weight, "cours": mk.price(t, i)})

    for i in range(first, len(cal)):
        if i > first:
            for t in values:
                values[t] *= ratio[i, cols[t]]
            if daily and i > first + 1:
                cash *= 1.0 + mk.rf[i]
        if pending is not None and pending[0] == i:
            _, kind, decision, decided, ridx, scores = pending
            pre = cash + sum(values.values())
            if kind == "revue":
                target = decision.target
                tgt_val = pre / len(target) if target else 0.0
                traded = sum(abs(tgt_val - values.get(t, 0.0)) for t in target)
                traded += sum(v for t, v in values.items() if t not in target)
                cost = traded * rate
                total = pre - cost
                tgt_val = total / len(target) if target else 0.0
                for t in list(values):
                    if t not in target:
                        why = decision.sell_reasons.get(t, "")
                        log_trade(i, "vente", t, decided, scores, why, "revue", values[t] / pre)
                        res.positions.append(closed(mk, t, meta.pop(t), i, why, "revue"))
                        del values[t]
                for t in target:
                    if t not in meta:
                        meta[t] = {"bought_review": ridx, "entry_pos": i}
                        log_trade(i, "achat", t, decided, scores, "", "revue", tgt_val / pre)
                    values[t] = tgt_val
                cash = total - tgt_val * len(target)
                res.turnover.append((cal[i], traded / 2 / (total + cost) if total > 0 else 0.0))
                res.reviews.append({"review_date": decided, "executed": cal[i],
                                    "buy": decision.buy, "sell": decision.sell})
            else:
                proceeds = 0.0
                blocked = set(decision.buy)      # vendu et racheté à la fois : le site garde
                for t in decision.sell:
                    if t not in values or t in blocked:
                        continue
                    why = decision.sell_reasons.get(t, "")
                    log_trade(i, "vente", t, decided, scores, why, "quotidien", values[t] / pre)
                    proceeds += values.pop(t)
                    res.positions.append(closed(mk, t, meta.pop(t), i, why, "quotidien"))
                cost = proceeds * rate
                cash += proceeds - cost
                spend = 0.0
                buys = [t for t in decision.buy if t not in values] if kind == "suivi" else []
                if buys and cash > 1e-12:
                    spend = cash / (1 + rate)
                    cost += spend * rate
                    each = spend / len(buys)
                    for t in buys:
                        values[t] = each
                        meta[t] = {"bought_review": ridx, "entry_pos": i}
                        log_trade(i, "achat", t, decided, scores, "", "quotidien", each / pre)
                    cash = 0.0
                traded = proceeds + spend
                res.turnover.append((cal[i], traded / 2 / pre if pre > 0 else 0.0))
            res.costs.append((cal[i], cost / pre if pre > 0 else 0.0))
            pending = None
        eq[i] = cash + sum(values.values())
        cash_w[i] = cash / eq[i] if eq[i] > 0 else np.nan
        npos[i] = len(values)
        if i + 1 >= len(cal):
            continue
        if i in review_pos:
            review_idx += 1
            scores = ranks[review_pos[i]]
            held = {t: m["bought_review"] for t, m in meta.items()}
            decision = review_decision(scores, held, params, review_idx)
            pending = (i + 1, "revue", decision, cal[i], review_idx, scores)
        elif daily and i in check_pos:
            scores = ranks[cal[i]]
            held = {t: m["bought_review"] for t, m in meta.items()}
            decision = review_decision(scores, held, params, review_idx)
            sells = [t for t in decision.sell if t not in decision.buy]
            buys = [t for t in decision.buy if t not in values]
            if mode == "vente_immediate" and sells:
                pending = (i + 1, "vente", decision, cal[i], review_idx, scores)
            elif mode == "suivi_quotidien" and (sells or (buys and cash > 1e-9)):
                pending = (i + 1, "suivi", decision, cal[i], review_idx, scores)

    res.equity = pd.Series(eq, index=cal).dropna()
    res.cash_weight = pd.Series(cash_w, index=cal).dropna()
    res.n_positions = pd.Series(npos, index=cal).dropna()
    for t, m in meta.items():
        res.holdings[t] = {"entry_date": cal[m["entry_pos"]],
                           "weight": values[t] / eq[len(cal) - 1]}

    # Ventes entre deux revues : l'étiquette aurait-elle disparu à la revue suivante, et
    # qu'a fait le titre vendu jusqu'à cette revue (comparé au S&P 500 équipondéré) ?
    rev_sorted = sorted(review_pos)
    for x in res.trades:
        if x["operation"] != "vente" or x["type"] != "quotidien":
            continue
        k = bisect.bisect_right(rev_sorted, x["pos"] - 1)
        if k >= len(rev_sorted) or rev_sorted[k] + 1 >= len(cal):
            continue
        rp = rev_sorted[k]
        sc = ranks[cal[rp]]
        t = x["ticker"]
        back = t in sc.index and bool(sc.at[t, "eligible"]) and \
            sc.at[t, "rank"] <= params["hold_rank"]
        x["dans_top50_a_la_revue_suivante"] = bool(back)
        x["rendement_jusqua_revue"] = growth(mk.px[x["pos"], cols[t]], mk.px[rp + 1, cols[t]])
        if mk.ew is not None:
            x["equipondere_jusqua_revue"] = growth(mk.px[x["pos"], mk.ew], mk.px[rp + 1, mk.ew])
    return res


def extra_stats(res: B.Result, mk: Market, start: str, end: str | None) -> dict:
    s = pd.Timestamp(start)
    e = pd.Timestamp(end) if end else mk.cal[-1]
    eqs = res.equity.loc[s:e]
    if len(eqs) < 60:
        return {}
    years = (eqs.index[-1] - eqs.index[0]).days / 365.25
    tr = [x for x in res.trades if s <= x["execution"] <= e]
    sells = [x for x in tr if x["operation"] == "vente"]
    buys = [x for x in tr if x["operation"] == "achat"]
    early = [x for x in sells if x["type"] == "quotidien"]
    costs = sum(c for d, c in res.costs if s <= d <= e)
    closed_p = [p for p in res.positions if s <= p["exit"] <= e]
    days = [(p["exit"] - p["entry"]).days for p in closed_p]

    # Rachats : un titre vendu puis racheté dans les trois mois
    buys_by_t: dict[str, list] = {}
    for x in res.trades:
        if x["operation"] == "achat":
            buys_by_t.setdefault(x["ticker"], []).append((x["pos"], x["cours"]))
    rebuys = []
    for x in sells:
        lst = buys_by_t.get(x["ticker"], [])
        k = bisect.bisect_right([p for p, _ in lst], x["pos"])
        if k < len(lst) and lst[k][0] - x["pos"] <= REBUY_WINDOW:
            g = growth(x["cours"], lst[k][1])
            if g is not None:
                rebuys.append(g)

    out = {
        "annees": years,
        "ventes_par_an": len(sells) / years, "achats_par_an": len(buys) / years,
        "ventes_hors_revue_par_an": len(early) / years,
        "ordres_par_an": (len(sells) + len(buys)) / years,
        "frais_par_an": costs / years,
        "duree_moyenne_jours": float(np.mean(days)) if days else None,
        "duree_mediane_jours": float(np.median(days)) if days else None,
        "liquidites_moyennes": float(res.cash_weight.loc[s:e].mean()),
        "lignes_moyennes": float(res.n_positions.loc[s:e].mean()),
        "rachats_3_mois": len(rebuys),
        "rachats_3_mois_part": len(rebuys) / len(sells) if sells else None,
        "rachat_ecart_median": float(np.median(rebuys)) if rebuys else None,
        "rachat_plus_cher_part": float(np.mean([r > 0 for r in rebuys])) if rebuys else None,
    }
    judged = [x for x in early if "dans_top50_a_la_revue_suivante" in x]
    if judged:
        out["ventes_hors_revue_revenues_top50_part"] = float(
            np.mean([x["dans_top50_a_la_revue_suivante"] for x in judged]))
        ex = [x["rendement_jusqua_revue"] - x["equipondere_jusqua_revue"] for x in judged
              if x.get("rendement_jusqua_revue") is not None
              and x.get("equipondere_jusqua_revue") is not None]
        if ex:
            out["vendus_tot_ecart_vs_equipondere_moyen"] = float(np.mean(ex))
            out["vendus_tot_ecart_vs_equipondere_median"] = float(np.median(ex))
            out["vendus_tot_battent_equipondere_part"] = float(np.mean([v > 0 for v in ex]))
            out["ventes_hors_revue_jugees"] = len(ex)
    return out


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    C.ensure_dirs()
    settings, protocol, concepts = C.settings(), C.protocol(), C.concepts()
    vetoes = C.vetoes()
    data = PL.collect(settings, concepts, offline=True)
    info, current, history = data["info"], data["current"], data["history"]
    states = PL.build_states(info, concepts)
    prices = P.load_prices()
    dropped = PL.drop_reused_tickers(info, prices, history)
    earn = {float(c): SEC.earnings_dates(int(c)) for c in info["cik"].dropna().unique()}
    ctx = FT.Context(prices=prices, states=states, info=info, history=history, current=current,
                     excluded_sectors=settings["universe"]["excluded_sectors"], earnings=earn,
                     market=settings["backtest"]["benchmarks"]["equal_weight"])
    cal = ctx.calendar
    today = cal[-1]
    log.info("Données jusqu'au %s, %d symboles réattribués écartés", today.date(), len(dropped))

    # Dates du site (fin de mois et revues), puis toutes les séances à partir de la première
    bt_start = pd.Timestamp(settings["backtest"]["start"])
    rev_months = sorted(set(settings["portfolio"]["review_months"]) |
                        {m for v in protocol.get("robustness", {}).values()
                         for m in v.get("review_months", [])})
    all_reviews = review_dates(cal[:-1], rev_months, settings["portfolio"]["review_day"], bt_start)
    official_dates = sorted(set(PL.month_ends(cal, bt_start)) | set(all_reviews))
    daily_dates = [d for d in cal if d >= official_dates[0]]
    log.info("Classement de chaque séance : %d séances du %s au %s", len(daily_dates),
             daily_dates[0].date(), daily_dates[-1].date())
    t1 = time.time()
    panel = {}
    for k, d in enumerate(daily_dates):
        panel[d] = PL.panel_frame(ctx, d, settings, vetoes)
        if k % 250 == 0:
            log.info("  %d/%d (%s), %.0fs", k + 1, len(daily_dates), d.date(), time.time() - t1)
    log.info("Classements calculés en %.0fs", time.time() - t1)

    min_elig = settings["backtest"]["min_eligible"]
    valid_start = next((d for d in official_dates
                        if int(panel[d]["eligible_base"].sum()) >= min_elig), None)
    if valid_start is None:
        raise RuntimeError("Jamais assez de titres éligibles")
    adj = prices["adj_close"].ffill()
    bench = {k: adj[v] for k, v in settings["backtest"]["benchmarks"].items() if v in adj}
    rf_sym = settings["backtest"]["risk_free"]
    rf_daily = (prices["close"][rf_sym].ffill() / 100 / 252) if rf_sym in prices["close"] else \
        pd.Series(0.0, index=cal)
    mk = Market(adj, rf_daily, settings["backtest"]["benchmarks"]["equal_weight"])
    min_f = settings["scoring"]["min_factors"]
    start = str(valid_start.date())
    design_end = str(pd.Timestamp(protocol["design_period"]["end"]).date())
    hold_start = protocol["holdout"]["start"]
    periods = {"conception": (start, design_end), "reservee": (hold_start, None),
               "totale": (start, None)}

    models = list(protocol["models"])
    results, verif, official = {}, {}, {}
    for model in models:
        t2 = time.time()
        params = C.portfolio_params(settings, protocol["variants"]["reference"], model)
        revs = [r for r in review_dates(cal[:-1], params["review_months"], params["review_day"],
                                        valid_start) if r in panel]
        ref = B.run(f"{model}:reference", panel, adj, params, revs, min_f)
        official[model] = {p: B.metrics(ref, bench, rf_daily, a, b)
                           for p, (a, b) in periods.items()}
        ranks = {d: B.rank_frame(panel[d], params, min_f) for d in daily_dates if d >= revs[0]}
        for mode in MODES:
            results[(model, mode)] = simulate(mode, mk, ranks, params, revs, model)
        sim = results[(model, "trimestriel")].equity
        a, b = sim.align(ref.equity, join="outer")
        verif[model] = {
            "ecart_relatif_max_trimestriel_vs_site": float((a / b - 1).abs().max()),
            "seances_simulees": int(len(sim)), "seances_site": int(len(ref.equity)),
            "revues": len(revs), "premiere_revue": revs[0], "derniere_revue": revs[-1],
            "positions_identiques": sorted(results[(model, "trimestriel")].holdings) ==
            sorted(ref.holdings),
        }
        log.info("%s : %d revues, écart max trimestriel vs site %.2e (%.0fs)", model, len(revs),
                 verif[model]["ecart_relatif_max_trimestriel_vs_site"], time.time() - t2)
        for mode in MODES:
            r = results[(model, mode)]
            log.info("  %-16s valeur finale %.3f, %d positions clôturées", mode,
                     r.equity.iloc[-1], len(r.positions))
        del ranks

    out = {
        "genere_le": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "donnees_jusquau": today, "debut": valid_start, "fin_conception": design_end,
        "debut_reservee": hold_start, "seances_classees": len(daily_dates),
        "frais_par_transaction": settings["portfolio"]["cost_per_trade"],
        "periodes": periods, "modeles": {},
    }
    for model in models:
        block = {"label": settings["models"][model]["label"], "site": official[model],
                 "strategies": {}}
        for mode in MODES:
            r = results[(model, mode)]
            block["strategies"][mode] = {
                p: {**B.metrics(r, bench, rf_daily, a, b), **extra_stats(r, mk, a, b)}
                for p, (a, b) in periods.items()}
            block["strategies"][mode]["lignes_finales"] = sorted(r.holdings)
        out["modeles"][model] = block
    (OUT / "comparaison.json").write_text(
        json.dumps(R.clean(out), ensure_ascii=False, indent=1), encoding="utf-8")

    curves = {f"{m}:{mo}": B.weekly(r.equity / r.equity.iloc[0]) for (m, mo), r in results.items()}
    for k, b in bench.items():
        s = b.loc[valid_start:].dropna()
        curves[k] = B.weekly(s / s.iloc[0])
    pd.DataFrame(curves).sort_index().to_csv(OUT / "courbes.csv", index_label="date")
    yearly = R.yearly_returns({**{f"{m}:{mo}": r.equity for (m, mo), r in results.items()},
                               **{k: v.loc[valid_start:] for k, v in bench.items()}}, today)
    pd.DataFrame(yearly).to_csv(OUT / "annees.csv", index=False)
    trades = pd.DataFrame([x for r in results.values() for x in r.trades]).drop(columns="pos")
    for c in ("decision", "execution"):
        trades[c] = pd.to_datetime(trades[c]).dt.date
    trades.to_csv(OUT / "operations.csv", index=False)
    (OUT / "verification.json").write_text(json.dumps(R.clean({
        "modeles": verif, "debut": valid_start, "donnees_jusquau": today,
        "seances_classees": len(daily_dates), "dates_du_site": len(official_dates),
        "duree_secondes": round(time.time() - t0)}), ensure_ascii=False, indent=1),
        encoding="utf-8")
    log.info("Terminé en %.0fs", time.time() - t0)
    return {"results": results, "market": mk, "reference_params": {
        m: C.portfolio_params(settings, protocol["variants"]["reference"], m) for m in models}}


if __name__ == "__main__":
    main()
