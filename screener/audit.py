"""Audit des données : couverture, biais de survivance, éligibilité."""
from __future__ import annotations

from collections import Counter

import pandas as pd

from .features import METRICS
from .scoring import REASONS


def build(*, info, prices, history, live, states, elig_counts, status, dropped, start) -> dict:
    adj = prices["adj_close"]
    last_day = adj.index[-1]
    start_ts = pd.Timestamp(start)

    hist_members = set()
    before = history[history["date"] <= start_ts]
    if not before.empty:
        hist_members |= set(before["tickers"].iloc[-1])
    for lst in history.loc[history["date"] > start_ts, "tickers"]:
        hist_members |= set(lst)
    current = set(info.index[info["current_member"]])
    former = sorted(hist_members - current)

    still_quoted, ended, never = [], [], []
    for t in former:
        if t in dropped or t not in adj.columns or adj[t].notna().sum() == 0:
            never.append(t)
            continue
        lv = adj[t].last_valid_index()
        (still_quoted if lv is not None and (last_day - lv).days <= 10 else ended).append(t)

    no_cik = sorted(t for t in hist_members if pd.isna(info["cik"].get(t)))
    excluded = set(live["sector"].dropna()) & {"Financials", "Real Estate"}
    core = live[~live["sector"].isin(excluded)]
    metric_cov = {m: float(core[m].notna().mean()) for m in METRICS if m in core}
    reason_counts = Counter(c for r in live["reasons"] for c in r)
    flag_counts = Counter(f.strip() for s in live.get("flags", pd.Series(dtype=str)).fillna("")
                          for f in str(s).split("|") if f.strip())
    return {
        "backtest_universe": {
            "start": start,
            "members_since_start": len(hist_members),
            "current_members": len(hist_members & current),
            "former_members": len(former),
            "former_still_quoted": len(still_quoted),
            "former_quotes_ended": len(ended),
            "former_without_prices": len(never),
            "former_without_prices_list": never[:300],
            "former_ended_list": ended[:300],
            "reused_symbols_dropped": dropped,
            "without_cik": no_cik[:300],
        },
        "sec_coverage": {
            "companies_with_states": int(states["cik"].nunique()) if len(states) else 0,
            "core_members": int(len(core)),
            "metric_coverage": metric_cov,
        },
        "eligibility_today": {REASONS.get(k, k): v for k, v in reason_counts.most_common()},
        "eligible_today": int(live["eligible"].sum()),
        "eligible_over_time": [{"date": str(d.date()), "eligible": n}
                               for d, n in sorted(elig_counts.items())],
        "flags": dict(flag_counts.most_common(10)),
        "status": status,
    }
