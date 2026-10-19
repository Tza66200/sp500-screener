"""Analyse ponctuelle (branche temporaire) : lignes du backtest de screener-sp500-web,
évaluées avec les cours ajustés du cache de ce dépôt, complétés par Yahoo si besoin.

Sorties dans resultats/ :
- web2_backtest.json, web2_etat.json, web2_classement.json : copies des fichiers publiés ;
- web2_ventes.csv : une ligne par position (achat et vente à la clôture suivant la décision) ;
- verification.json : couverture des cours et reconstitution de la courbe publiée.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from screener import prices as P  # noqa: E402

OUT = Path("resultats")
OUT.mkdir(exist_ok=True)
BASE = "https://tza66200.github.io/screener-sp500-web/data/"


def get(name: str):
    local = os.environ.get("WEB2_LOCAL")          # essai hors ligne
    if local:
        content = (Path(local) / name).read_bytes()
    else:
        r = requests.get(BASE + name, timeout=180, headers={"Cache-Control": "no-cache"})
        r.raise_for_status()
        content = r.content
    (OUT / f"web2_{name}").write_bytes(content)
    return json.loads(content)


bt = get("backtest.json")
etat = get("etat.json")
try:
    get("classement.json")
except Exception as exc:  # noqa: BLE001
    print("classement.json indisponible :", exc)
print("Backtest publié :", bt.get("debut"), "->", bt.get("fin"), "généré le", bt.get("genere_le"),
      "empreinte", bt.get("empreinte"))

px = P.load_prices()
adj = px["adj_close"].sort_index()
fin = pd.Timestamp(bt["fin"])
cal = adj["^SP500TR"].dropna().index
cal = cal[cal <= fin]
print("Calendrier :", cal[0].date(), "->", cal[-1].date(), len(cal), "séances")

journal = bt["journal"]
frais = float(bt.get("reglages", {}).get("frais", 0.001))


def pos(d: pd.Timestamp) -> int:
    """Dernière séance <= d."""
    return int(cal.searchsorted(d, side="right") - 1)


# --- Positions reconstituées à partir du journal ----------------------------------
held: dict[str, tuple] = {}
lignes = []
prev: set[str] = set()
ecarts = []
for e in journal:
    d = pd.Timestamp(e["date"])
    ex = cal[min(pos(d) + 1, len(cal) - 1)]
    cur = set(e["portefeuille"])
    sorties, entrees = prev - cur, cur - prev
    if set(e["ventes"]) != sorties or set(e["achats"]) - entrees:
        ecarts.append({"date": e["date"], "ventes": e["ventes"], "sorties": sorted(sorties),
                       "achats": e["achats"], "entrees": sorted(entrees)})
    for t in sorted(sorties):
        a, da = held.pop(t)
        lignes.append({"Ticker": t, "Décision d'achat": da.date(), "Achat": a.date(),
                       "Décision de vente": d.date(), "Vente": ex.date(), "Statut": "vendue",
                       "Type de vente": "revue trimestrielle" if e["rebalancement"] else "vente d'urgence"})
    for t in sorted(entrees):
        held[t] = (ex, d)
    prev = cur
for t, (a, da) in held.items():
    lignes.append({"Ticker": t, "Décision d'achat": da.date(), "Achat": a.date(),
                   "Décision de vente": None, "Vente": None, "Statut": "détenue", "Type de vente": ""})
L = pd.DataFrame(lignes)
print("Positions :", len(L), "dont vendues", int((L["Statut"] == "vendue").sum()),
      "| écarts journal/portefeuille :", len(ecarts))

# --- Cours : cache de ce dépôt, sinon Yahoo -----------------------------------------
need = sorted(set(L["Ticker"]))
first_entry = L.groupby("Ticker")["Achat"].min()
series: dict[str, pd.Series] = {}
a_telecharger = []
for t in need:
    s = adj[t].dropna() if t in adj.columns else pd.Series(dtype=float)
    if len(s) and s.index[0] <= pd.Timestamp(first_entry[t]):
        series[t] = s
    else:
        a_telecharger.append(t)
print("Cours en cache :", len(series), "| à télécharger :", len(a_telecharger), a_telecharger[:40])
source_yahoo = []
if a_telecharger:
    import yfinance as yf
    for k in range(0, len(a_telecharger), 40):
        lot = a_telecharger[k:k + 40]
        raw = yf.download(lot, start="2009-06-01", auto_adjust=False, progress=False,
                          group_by="column", threads=True)
        if raw is None or raw.empty:
            continue
        ac = raw["Adj Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Adj Close"]].rename(
            columns={"Adj Close": lot[0]})
        for t in lot:
            if t in ac.columns and ac[t].notna().any():
                series[t] = ac[t].dropna()
                source_yahoo.append(t)
manquants = [t for t in need if t not in series]
print("Téléchargés :", len(source_yahoo), "| toujours manquants :", manquants)

on_cal = {t: s.reindex(cal.union(s.index)).ffill().reindex(cal) for t, s in series.items()}


def valeur(t, d):
    s = on_cal.get(t)
    if s is None or d is None or pd.isna(d):
        return np.nan
    return s.iloc[pos(pd.Timestamp(d))]


def bench(col, a, b):
    s = adj[col].reindex(cal).ffill()
    v0, v1 = s.iloc[pos(pd.Timestamp(a))], s.iloc[pos(pd.Timestamp(b))]
    return float(v1 / v0 - 1) if v0 and np.isfinite(v0) and np.isfinite(v1) else np.nan


rend, sp, ew, jours = [], [], [], []
for r in L.itertuples(index=False):
    b = r.Vente if r.Statut == "vendue" else cal[-1]
    p0, p1 = valeur(r.Ticker, r.Achat), valeur(r.Ticker, b)
    rend.append(p1 / p0 - 1 if p0 and np.isfinite(p0) and np.isfinite(p1) else np.nan)
    sp.append(bench("^SP500TR", r.Achat, b))
    ew.append(bench("RSP", r.Achat, b))
    jours.append(int((pd.Timestamp(b) - pd.Timestamp(r.Achat)).days))
L["Jours détenus"] = jours
L["Rendement"] = np.round(rend, 6)
L["S&P 500 même période"] = np.round(sp, 6)
L["Équipondéré même période"] = np.round(ew, 6)
L.sort_values(["Achat", "Ticker"]).to_csv(OUT / "web2_ventes.csv", index=False, encoding="utf-8-sig")

# --- Reconstitution de la courbe publiée (contrôle) ----------------------------------
R = pd.DataFrame({t: s.pct_change().fillna(0.0) for t, s in on_cal.items()}).reindex(cal).fillna(0.0)
n = len(cal)
nav = pd.Series(np.nan, index=cal)
j0 = pos(pd.Timestamp(journal[0]["date"]))
nav.iloc[j0] = 1.0
positions: dict[str, float] = {}
cash, j_last = 1.0, j0


def avancer(ja, jb):
    global positions
    if jb <= ja:
        return
    if positions:
        tick = [t for t in positions]
        g = (1.0 + R.iloc[ja + 1: jb + 1][tick]).cumprod().values
        vals = g * np.array([positions[t] for t in tick])[None, :]
        nav.iloc[ja + 1: jb + 1] = vals.sum(axis=1) + cash
        positions = {t: float(vals[-1, c]) for c, t in enumerate(tick)}
    else:
        nav.iloc[ja + 1: jb + 1] = cash


for e in journal:
    i = pos(pd.Timestamp(e["date"]))
    ex = min(i + 1, n - 1)
    avancer(j_last, ex)
    j_last = ex
    val = sum(positions.values()) + cash
    if e["rebalancement"]:
        cible = list(e["portefeuille"])
        w = 1.0 / len(cible) if cible else 0.0
        union = set(positions) | set(cible)
        rot = sum(abs((w * val if t in cible else 0.0) - positions.get(t, 0.0)) for t in union)
        nette = val - frais * rot
        positions = {t: w * nette for t in cible}
        cash = 0.0 if cible else nette
    else:
        for t in e["ventes"]:
            if t in positions:
                v = positions.pop(t)
                cash += v * (1 - frais)
avancer(j_last, n - 1)

ser = bt["series"]
k = ser["noms"].index("Stratégie")
pub = pd.Series(ser["valeurs"][k], index=pd.to_datetime(ser["dates"])).dropna()
mine = nav.reindex(pub.index).ffill()
ratio = (mine / mine.iloc[0]) / (pub / pub.iloc[0])
verif = {
    "backtest_genere_le": bt.get("genere_le"), "backtest_debut": bt.get("debut"), "backtest_fin": bt.get("fin"),
    "empreinte": bt.get("empreinte"), "positions": int(len(L)),
    "ventes": int((L["Statut"] == "vendue").sum()), "ecarts_journal": ecarts[:20],
    "n_ecarts_journal": len(ecarts), "tickers": len(need), "telecharges_yahoo": source_yahoo,
    "manquants": manquants, "rendements_manquants": int(L["Rendement"].isna().sum()),
    "courbe_publiee_fin": float(pub.iloc[-1] / pub.iloc[0]),
    "courbe_reconstituee_fin": float(mine.iloc[-1] / mine.iloc[0]),
    "ecart_relatif_max": float((ratio - 1).abs().max()),
    "ecart_relatif_fin": float(ratio.iloc[-1] - 1),
}
(OUT / "verification.json").write_text(json.dumps(verif, ensure_ascii=False, indent=1, default=str))
print(json.dumps({k: v for k, v in verif.items() if k != "ecarts_journal"}, ensure_ascii=False, default=str))
