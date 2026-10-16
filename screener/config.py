"""Chargement de la configuration et chemins du projet."""
from __future__ import annotations

import copy
import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = Path(os.environ.get("SCREENER_CONFIG_DIR", ROOT / "config"))
DATA_DIR = Path(os.environ.get("SCREENER_DATA_DIR", ROOT / "data"))
SITE_DIR = ROOT / "site"
SITE_DATA_DIR = Path(os.environ.get("SCREENER_SITE_DATA_DIR", SITE_DIR / "data"))
HISTORY_DIR = Path(os.environ.get("SCREENER_HISTORY_DIR", ROOT / "history"))

FACTORS = ["growth", "earnings", "momentum", "quality", "value", "risk"]
FACTOR_LABELS = {
    "growth": "Croissance",
    "earnings": "Résultats",
    "momentum": "Momentum",
    "quality": "Qualité",
    "value": "Valorisation",
    "risk": "Risque",
}


def _load(name: str) -> dict:
    with open(CONFIG_DIR / name, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def settings() -> dict:
    return _load("settings.yaml")


def protocol() -> dict:
    return _load("protocol.yaml")


def concepts() -> dict:
    return _load("xbrl_concepts.yaml")


def vetoes() -> list[dict]:
    return (_load("vetoes.yaml") or {}).get("vetoes") or []


def model_weights(base: dict, model: str) -> dict:
    w = {f: float(base["models"][model]["weights"].get(f, 0.0)) for f in FACTORS}
    return w


def portfolio_params(base: dict, overrides: dict | None = None, model: str | None = None) -> dict:
    """Paramètres de portefeuille + pondérations d'un modèle, avec surcharges d'une variante.

    `weights` dans une surcharge peut valoir "equal" (poids égaux entre les facteurs utilisés
    par le modèle) ou un dictionnaire, éventuellement indexé par modèle."""
    model = model or base["default_model"]
    params = copy.deepcopy(base["portfolio"])
    params["model"] = model
    params["weights"] = model_weights(base, model)
    for key, value in (overrides or {}).items():
        if key == "weights":
            if value == "equal":
                active = [f for f, w in params["weights"].items() if w > 0]
                value = {f: (1 / len(active) if f in active else 0.0) for f in FACTORS}
            elif isinstance(value, dict) and model in value:
                value = value[model]
            value = {f: float(value.get(f, 0.0)) for f in FACTORS}
        params[key] = copy.deepcopy(value)
    total = sum(params["weights"].values())
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"Les pondérations doivent sommer à 1 (somme = {total})")
    return params


def ensure_dirs() -> None:
    for d in (DATA_DIR, DATA_DIR / "sec" / "facts", DATA_DIR / "sec" / "submissions",
              SITE_DATA_DIR, HISTORY_DIR):
        d.mkdir(parents=True, exist_ok=True)
