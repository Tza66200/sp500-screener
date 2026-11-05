"""Règles de construction du portefeuille modèle."""
from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd


@dataclass
class Decision:
    keep: list[str]
    buy: list[str]
    sell: list[str]
    sell_reasons: dict[str, str]

    @property
    def target(self) -> list[str]:
        return self.keep + self.buy


def max_per_sector(params: dict) -> int:
    # + 1e-9 : 20 x 0,15 doit donner 3 même si le produit tombe juste sous l'entier
    return max(1, math.floor(params["n_positions"] * params["max_sector_fraction"] + 1e-9))


def review_decision(scores: pd.DataFrame, held: dict[str, int], params: dict,
                    review_index: int, entry_dates: dict | None = None,
                    when: pd.Timestamp | None = None) -> Decision:
    """Décide des titres à garder, vendre et acheter lors d'une revue.

    scores      : index ticker, colonnes eligible, rank, sector.
    held        : ticker -> numéro de la revue d'achat.
    entry_dates : ticker -> date d'achat ; avec `when` (date de la revue), sert à la durée
                  minimale de détention (params « min_hold_days ») : une ligne plus jeune
                  n'est pas vendue sur son rang, sauf au-delà de hold_rank x hard_exit_mult.
    """
    n = params["n_positions"]
    cap = max_per_sector(params)
    hold_rank = params["hold_rank"]
    min_days = params.get("min_hold_days") or 0
    hard_rank = hold_rank * params.get("hard_exit_mult", 3)
    eligible = scores[scores["eligible"]].sort_values("rank")
    keep, sell_reasons = [], {}
    for t, bought_at in held.items():
        if t not in eligible.index:
            sell_reasons[t] = "n'est plus éligible"
            continue
        rank = eligible.at[t, "rank"]
        entry = (entry_dates or {}).get(t)
        young = bool(min_days and entry is not None and when is not None
                     and (pd.Timestamp(when) - pd.Timestamp(entry)).days < min_days)
        if params.get("holding") == "fixed_12m":
            if review_index - bought_at >= 4:
                if rank <= n:
                    keep.append(t)     # détention échue, mais toujours dans le top N
                else:
                    sell_reasons[t] = "détention de 12 mois échue"
            else:
                keep.append(t)
        elif rank <= hold_rank or (young and rank <= hard_rank):
            keep.append(t)
        elif young:
            sell_reasons[t] = (f"tombé au-delà du rang {int(hard_rank)} (rang {int(rank)}) "
                               f"avant {min_days // 29} mois de détention")
        else:
            sell_reasons[t] = f"sorti du top {hold_rank} (rang {int(rank)})"
    count: dict[str, int] = {}
    for t in keep:
        s = eligible.at[t, "sector"]
        count[s] = count.get(s, 0) + 1
    buy = []
    for t, row in eligible.iterrows():
        if len(keep) + len(buy) >= n:
            break
        if t in keep:
            continue
        s = row["sector"]
        if count.get(s, 0) >= cap:
            continue
        buy.append(t)
        count[s] = count.get(s, 0) + 1
    return Decision(keep=keep, buy=buy, sell=list(sell_reasons), sell_reasons=sell_reasons)


def review_dates(calendar: pd.DatetimeIndex, months: list[int], day: int,
                 start: pd.Timestamp, end: pd.Timestamp | None = None) -> list[pd.Timestamp]:
    """Première séance à partir du `day` de chaque mois de revue."""
    end = end or calendar[-1]
    out = []
    for year in range(start.year, end.year + 1):
        for m in months:
            target = pd.Timestamp(year=year, month=m, day=day)
            if target < start or target > end:
                continue
            i = calendar.searchsorted(target, side="left")
            if i < len(calendar):
                out.append(calendar[i])
    return sorted(set(out))


def next_review(today: pd.Timestamp, months: list[int], day: int) -> pd.Timestamp:
    for year in (today.year, today.year + 1):
        for m in months:
            d = pd.Timestamp(year=year, month=m, day=day)
            if d > today:
                return d
    raise ValueError("aucune revue future")
