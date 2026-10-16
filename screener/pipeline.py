"""Point d'entrée : collecte, calculs, backtest, rapports.

    python -m screener.pipeline run              # tout (téléchargements compris)
    python -m screener.pipeline run --offline    # recalcul à partir des données en cache
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from pandas.tseries.offsets import BDay

from . import audit as A
from . import backtest as B
from . import config as C
from . import features as FT
from . import fundamentals as FD
from . import ic as IC
from . import prices as P
from . import report as R
from . import scoring as S
from . import sec as SEC
from . import universe as U
from .portfolio import next_review, review_dates, review_decision

log = logging.getLogger("screener")


# ----------------------------------------------------------------------------
# Étape 1 : données
# ----------------------------------------------------------------------------

def collect(settings: dict, concepts: dict, offline: bool) -> dict:
    status: dict = {"warnings": []}
    data_cfg = settings["data"]
    if offline:
        current, history = U.load_universe()
        info = pd.read_parquet(C.DATA_DIR / "ticker_info.parquet").set_index("ticker")
        status.update(json.loads((C.DATA_DIR / "collect_status.json").read_text()))
        return {"current": current, "history": history, "info": info, "status": status}

    t0 = time.time()
    current = U.fetch_current_constituents()
    history = U.fetch_membership_history()
    U.save_universe(current, history)
    status["constituents_source"] = current["source"].iloc[0]
    status["history_last_date"] = str(history["date"].iloc[-1].date())
    log.info("Univers : %d membres actuels, historique jusqu'au %s",
             len(current), status["history_last_date"])

    first_needed = (pd.Timestamp(settings["backtest"]["start"]) - pd.Timedelta(days=400))
    tickers = U.all_members_since(history, current, str(first_needed.date()))
    secmap = U.fetch_sec_ticker_map().set_index("ticker")
    cur = current.set_index("ticker")
    info = pd.DataFrame(index=pd.Index(tickers, name="ticker"))
    info["name"] = cur["name"].reindex(tickers)
    info["sector"] = cur["sector"].reindex(tickers)
    info["sub_industry"] = cur["sub_industry"].reindex(tickers)
    info["cik"] = cur["cik"].reindex(tickers).astype("Float64")
    missing = info["cik"].isna()
    info.loc[missing, "cik"] = secmap["cik"].reindex(info.index[missing]).astype("Float64")
    info.loc[info["name"].isna(), "name"] = secmap["title"].reindex(info.index[info["name"].isna()])
    info["current_member"] = info.index.isin(cur.index)

    # Cours
    bench = list(settings["backtest"]["benchmarks"].values()) + [settings["backtest"]["risk_free"]]
    pstat = P.update_prices(tickers + bench, data_cfg["history_start"], data_cfg["price_chunk"],
                            data_cfg["price_pause_seconds"])
    status["prices"] = pstat
    log.info("Cours : %d/%d titres, dernière séance %s", pstat["downloaded"], pstat["requested"],
             pstat["last_date"])
    for b in bench:
        if b in pstat["failed"]:
            status["warnings"].append(f"Indice de référence indisponible : {b}")

    # SEC
    ciks = sorted({int(c) for c in info["cik"].dropna()})
    sstat = SEC.refresh(ciks, concepts, per_second=data_cfg["sec_requests_per_second"])
    status["sec"] = {k: (v if not isinstance(v, list) else len(v)) for k, v in sstat.items()}
    status["sec"]["errors_sample"] = sstat["errors"][:10]
    status["sec_refreshed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    log.info("SEC : %d dépôts lus, %d jeux de faits mis à jour, %d erreurs",
             sstat["submissions_ok"], sstat["facts_updated"], len(sstat["errors"]))

    # Anciens membres : le CIK trouvé via la table actuelle de la SEC peut appartenir à une
    # autre société qui a repris le symbole. On ne le garde que si la société déposait déjà
    # des comptes avant la sortie de l'indice.
    exits = exit_dates(history)
    reassigned = []
    for t in info.index[~info["current_member"] & info["cik"].notna()]:
        facts = SEC.load_facts(int(info.at[t, "cik"]))
        ex = exits.get(t)
        if ex is None:
            continue
        if facts is None or facts.empty or facts["filed"].min() > ex:
            info.at[t, "cik"] = pd.NA
            reassigned.append(t)
    status["sec_cik_rejected"] = reassigned
    if reassigned:
        log.info("CIK écartés (symbole repris par une autre société) : %s", ", ".join(reassigned))

    # Secteur des anciens membres : code SIC
    comp = SEC.load_companies().set_index("cik")
    no_sector = info["sector"].isna() & info["cik"].notna()
    sic = info.loc[no_sector, "cik"].map(lambda c: comp["sic"].get(int(c)) if int(c) in comp.index
                                         else None)
    info.loc[no_sector, "sector"] = sic.map(U.sic_to_sector)
    info["sector_source"] = np.where(info["current_member"], "GICS", "SIC (approximation)")

    info.reset_index().to_parquet(C.DATA_DIR / "ticker_info.parquet", index=False)
    status["collect_seconds"] = round(time.time() - t0)
    (C.DATA_DIR / "collect_status.json").write_text(json.dumps(status, default=str))
    return {"current": current, "history": history, "info": info, "status": status}


def build_states(info: pd.DataFrame, concepts: dict) -> pd.DataFrame:
    t0 = time.time()
    frames = []
    for cik in sorted({int(c) for c in info["cik"].dropna()}):
        facts = SEC.load_facts(cik)
        if facts is None or facts.empty:
            continue
        try:
            st = FD.company_states(facts, concepts)
        except Exception as exc:  # noqa: BLE001
            log.warning("États fondamentaux CIK %s : %s", cik, exc)
            continue
        st.insert(0, "cik", cik)
        frames.append(st)
    states = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["cik"] + FD.STATE_COLUMNS)
    states["usable_date"] = states["known_date"] + BDay(1)
    states.to_parquet(C.DATA_DIR / "fundamental_states.parquet", index=False)
    log.info("États fondamentaux : %d lignes pour %d sociétés (%.0fs)", len(states),
             states["cik"].nunique(), time.time() - t0)
    return states


def exit_dates(history: pd.DataFrame) -> dict[str, pd.Timestamp]:
    """Date de la dernière sortie de l'indice (première date où le titre est absent)."""
    out: dict[str, pd.Timestamp] = {}
    prev: set[str] = set()
    for d, lst in zip(history["date"], history["tickers"]):
        cur = set(lst)
        for t in prev - cur:
            out[t] = d
        prev = cur
    for t in prev:
        out.pop(t, None)                # toujours membre
    return out


def drop_reused_tickers(info: pd.DataFrame, prices: dict, history: pd.DataFrame) -> list[str]:
    """Anciens symboles réattribués à une autre société : la série Yahoo commence après la
    sortie de l'indice. On les retire pour ne pas mélanger deux entreprises."""
    last_member = exit_dates(history)
    adj = prices["adj_close"]
    dropped = []
    for t in info.index[~info["current_member"]]:
        if t not in adj.columns or t not in last_member:
            continue
        first_valid = adj[t].first_valid_index()
        if first_valid is not None and first_valid > last_member[t]:
            dropped.append(t)
    for name in ("adj_close", "close", "volume"):
        prices[name] = prices[name].drop(columns=[c for c in dropped if c in prices[name]])
    return dropped


# ----------------------------------------------------------------------------
# Étape 2 : scores
# ----------------------------------------------------------------------------

def vetoes_at(vetoes: list[dict], when: pd.Timestamp) -> dict:
    out = {}
    for v in vetoes:
        start = pd.Timestamp(v.get("date", "1900-01-01"))
        until = pd.Timestamp(v["until"]) if v.get("until") else pd.Timestamp("2200-01-01")
        if start <= when <= until:
            out[U.norm_ticker(v["ticker"])] = v.get("reason", "")
    return out


def panel_frame(ctx: FT.Context, when: pd.Timestamp, settings: dict, vetoes: list[dict]
                ) -> pd.DataFrame:
    feats = FT.compute(ctx, when, live=False)
    scored = S.score(feats, settings["weights"], settings)
    filt = S.apply_filters(scored, settings, vetoes=vetoes_at(vetoes, when))
    out = filt[["sector", *C.FACTORS, "composite", "above_sma200"]].copy()
    out["scorable"] = scored["reasons"].map(len) == 0
    out["eligible_base"] = filt["eligible"]
    return out


def build_panel(ctx: FT.Context, dates: list[pd.Timestamp], settings: dict, vetoes: list[dict]
                ) -> dict:
    t0 = time.time()
    panel = {}
    for k, d in enumerate(dates):
        panel[d] = panel_frame(ctx, d, settings, vetoes)
        if k % 50 == 0:
            log.info("Scores historiques : %d/%d (%s)", k + 1, len(dates), d.date())
    log.info("Scores historiques calculés pour %d dates (%.0fs)", len(dates), time.time() - t0)
    return panel


def month_ends(cal: pd.DatetimeIndex, start: pd.Timestamp) -> list[pd.Timestamp]:
    s = pd.Series(cal, index=cal)
    s = s[s >= start]
    return list(s.groupby([s.index.year, s.index.month]).max())


def merger_flags(info: pd.DataFrame, when: pd.Timestamp, settings: dict) -> dict:
    forms = settings["data"]["merger_forms"]
    since = when - pd.Timedelta(days=settings["data"]["merger_lookback_days"])
    out = {}
    for t, cik in info["cik"].dropna().items():
        fl = SEC.load_filings(int(cik))
        if fl is None or fl.empty:
            continue
        hit = fl[fl["form"].isin(forms) & (fl["filingDate"] >= since)]
        if len(hit):
            last = hit.sort_values("filingDate").iloc[-1]
            out[t] = f"{last['form']} déposé le {last['filingDate'].date()}"
    return out


def earnings_dates(cik, when: pd.Timestamp) -> tuple[str | None, str | None]:
    if cik is None or pd.isna(cik):
        return None, None
    fl = SEC.load_filings(int(cik))
    if fl is None or fl.empty:
        return None, None
    e = fl[(fl["form"] == "8-K") & fl["items"].fillna("").str.contains("2.02", regex=False)]
    dates = sorted(e["filingDate"].dropna())
    if not dates:
        return None, None
    last = dates[-1]
    cands = [d + pd.Timedelta(days=364) for d in dates
             if when < d + pd.Timedelta(days=364) <= when + pd.Timedelta(days=120)]
    nxt = min(cands) if cands else last + pd.Timedelta(days=91)
    return str(last.date()), str(nxt.date())


# ----------------------------------------------------------------------------
# Programme principal
# ----------------------------------------------------------------------------

def run(offline: bool = False) -> None:
    C.ensure_dirs()
    settings, protocol, concepts = C.settings(), C.protocol(), C.concepts()
    vetoes = C.vetoes()
    data = collect(settings, concepts, offline)
    info, current, history, status = data["info"], data["current"], data["history"], data["status"]

    states = build_states(info, concepts)
    prices = P.load_prices()
    dropped = drop_reused_tickers(info, prices, history)
    if dropped:
        log.info("Symboles réattribués écartés : %s", ", ".join(dropped))

    ctx = FT.Context(prices=prices, states=states, info=info, history=history, current=current,
                     excluded_sectors=settings["universe"]["excluded_sectors"])
    cal = ctx.calendar
    today = cal[-1]

    # Classement courant (membres actuels, OPA et vetos)
    live_feats = FT.compute(ctx, today, live=True)
    live_scored = S.score(live_feats, settings["weights"], settings)
    merger = merger_flags(info.reindex(live_scored.index), today, settings)
    live_vetoes = vetoes_at(vetoes, today)
    live = S.apply_filters(live_scored, settings, merger=merger, vetoes=live_vetoes)
    live["reason_text"] = [S.reason_text(r, merger, live_vetoes, t)
                           for t, r in zip(live.index, live["reasons"])]
    ed = {t: earnings_dates(c, today) for t, c in live["cik"].items()}
    live["last_earnings"] = [ed[t][0] for t in live.index]
    live["next_earnings_est"] = [ed[t][1] for t in live.index]
    log.info("Classement du %s : %d éligibles sur %d", today.date(), int(live["eligible"].sum()),
             len(live))

    # Scores historiques
    bt_start = pd.Timestamp(settings["backtest"]["start"])
    rev_months = sorted({m for m in settings["portfolio"]["review_months"]} |
                        {m for v in protocol.get("robustness", {}).values()
                         for m in v.get("review_months", [])})
    all_reviews = review_dates(cal[:-1], rev_months, settings["portfolio"]["review_day"], bt_start)
    dates = sorted(set(month_ends(cal, bt_start)) | set(all_reviews))
    panel = build_panel(ctx, dates, settings, vetoes)

    # Première revue avec assez de titres éligibles
    min_elig = settings["backtest"]["min_eligible"]
    elig_counts = {d: int(df["eligible_base"].sum()) for d, df in panel.items()}
    valid_start = next((d for d in sorted(elig_counts) if elig_counts[d] >= min_elig), None)
    if valid_start is None:
        raise RuntimeError("Jamais assez de titres éligibles pour lancer le backtest")

    adj = prices["adj_close"].ffill()
    bench_series = {k: adj[v] for k, v in settings["backtest"]["benchmarks"].items() if v in adj}
    rf = settings["backtest"]["risk_free"]
    rf_daily = (prices["close"][rf].ffill() / 100 / 252) if rf in prices["close"] else \
        pd.Series(0.0, index=cal)

    runs: dict[str, B.Result] = {}
    groups = {"variants": protocol["variants"], "robustness": protocol.get("robustness", {})}
    for group, specs in groups.items():
        for name, overrides in specs.items():
            params = C.portfolio_params(settings, overrides)
            revs = [r for r in review_dates(cal[:-1], params["review_months"],
                                            params["review_day"], valid_start) if r in panel]
            runs[name] = B.run(name, panel, adj, params, revs, settings["scoring"]["min_factors"])
            log.info("Backtest %s : %d revues", name, len(revs))

    ic_end = today if protocol["holdout"]["revealed"] else pd.Timestamp(protocol["design_period"]["end"])
    ic_panel = {d: df for d, df in panel.items() if d in set(month_ends(cal, valid_start))}
    ic_obs = IC.ic_observations(ic_panel, adj, protocol["ic_horizons_months"], ic_end)

    # Portefeuille modèle courant et revue hypothétique aujourd'hui
    ref = runs["reference"]
    ref_params = C.portfolio_params(settings, protocol["variants"]["reference"])
    held = {t: h["bought_review"] for t, h in ref.holdings.items()}
    hypo = review_decision(live[["eligible", "rank", "sector"]], held, ref_params,
                           len(ref.reviews))
    nrev = next_review(today, ref_params["review_months"], ref_params["review_day"])

    audit = A.build(info=info, prices=prices, history=history, live=live, states=states,
                    elig_counts=elig_counts, status=status, dropped=dropped,
                    start=str(valid_start.date()))
    R.write_all(settings=settings, protocol=protocol, live=live, runs=runs, groups=groups,
                bench=bench_series, rf_daily=rf_daily, ic_obs=ic_obs, audit=audit,
                status=status, hypo=hypo, next_review_date=nrev, today=today,
                valid_start=valid_start, prices=prices, panel_dates=len(panel))
    log.info("Terminé.")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["run"])
    ap.add_argument("--offline", action="store_true", help="recalcul sans téléchargement")
    args = ap.parse_args()
    run(offline=args.offline)


if __name__ == "__main__":
    main()
