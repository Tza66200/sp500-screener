"""Accès HTTP : reprises sur erreur, limite de débit pour la SEC."""
from __future__ import annotations

import logging
import os
import threading
import time

import requests

log = logging.getLogger(__name__)

BROWSER_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


def sec_user_agent() -> str:
    email = os.environ.get("SEC_CONTACT_EMAIL", "").strip()
    if not email or "@" not in email:
        raise RuntimeError(
            "SEC_CONTACT_EMAIL manquant : la SEC exige une adresse de contact dans chaque requête."
        )
    return f"sp500-screener {email}"


class RateLimiter:
    def __init__(self, per_second: float):
        self.interval = 1.0 / per_second
        self.lock = threading.Lock()
        self.next_time = 0.0

    def wait(self) -> None:
        with self.lock:
            now = time.monotonic()
            if now < self.next_time:
                time.sleep(self.next_time - now)
            self.next_time = max(now, self.next_time) + self.interval


def get(url: str, *, headers: dict | None = None, limiter: RateLimiter | None = None,
        retries: int = 5, timeout: float = 30.0, session: requests.Session | None = None,
        allow_404: bool = False) -> requests.Response | None:
    """GET avec reprises exponentielles. Renvoie None sur 404 si allow_404."""
    sess = session or requests
    delay = 2.0
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        if limiter:
            limiter.wait()
        try:
            resp = sess.get(url, headers=headers, timeout=timeout)
            if resp.status_code == 404 and allow_404:
                return None
            if resp.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"HTTP {resp.status_code}", response=resp)
            resp.raise_for_status()
            return resp
        except (requests.RequestException,) as exc:  # noqa: PERF203
            last_exc = exc
            if attempt == retries:
                break
            log.warning("GET %s échec (%s), nouvel essai dans %.0fs", url, exc, delay)
            time.sleep(delay)
            delay = min(delay * 2, 60)
    raise RuntimeError(f"Échec définitif pour {url}: {last_exc}")
