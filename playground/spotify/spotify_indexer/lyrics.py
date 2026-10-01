import re
import threading
import time

import httpx

from .config import Config
from .spotify import Track

LRCLIB_BASE = "https://lrclib.net"
USER_AGENT = "homelab-spotify-indexer/0.1"
RETRIES = 3

_client: httpx.Client | None = None
_limiter: "RateLimiter | None" = None


class RateLimiter:
    def __init__(self, min_interval: float):
        self.min_interval = min_interval
        self.next_time = 0.0
        self.lock = threading.Lock()

    def acquire(self) -> None:
        with self.lock:
            now = time.monotonic()
            wait = self.next_time - now
            self.next_time = max(now, self.next_time) + self.min_interval
        if wait > 0:
            time.sleep(wait)


def init(cfg: Config) -> None:
    global _client, _limiter
    _client = httpx.Client(timeout=15, headers={"User-Agent": USER_AGENT})
    _limiter = RateLimiter(cfg.lyrics_min_interval)


def _request(path: str, params: dict) -> httpx.Response | None:
    resp = None
    for attempt in range(RETRIES):
        try:
            _limiter.acquire()
            resp = _client.get(f"{LRCLIB_BASE}{path}", params=params)
            if resp.status_code == 429:
                try:
                    delay = float(resp.headers.get("Retry-After"))
                except (TypeError, ValueError):
                    delay = 2**attempt * 2
                time.sleep(delay)
                continue
            if resp.status_code >= 500:
                time.sleep(2**attempt * 2)
                continue
            return resp
        except httpx.HTTPError:
            if attempt == RETRIES - 1:
                return None
            time.sleep(2**attempt * 2)
    return resp


def _strip_timestamps(synced: str) -> str:
    return re.sub(r"\[[^\]]*\]", "", synced)


def fetch_lyrics(track: Track) -> str | None:
    resp = _request(
        "/api/get",
        {
            "artist_name": track.artists[0],
            "track_name": track.name,
            "album_name": track.album or "",
            "duration": track.duration_ms // 1000,
        },
    )
    if resp is not None and resp.status_code == 200:
        body = resp.json()
        plain = body.get("plainLyrics") or _strip_timestamps(body.get("syncedLyrics") or "")
        if plain.strip():
            return plain.strip()

    resp = _request("/api/search", {"q": f"{track.artists[0]} {track.name}"})
    if resp is None or resp.status_code != 200:
        return None
    results = resp.json()
    duration = track.duration_ms // 1000
    candidates = [
        r
        for r in results
        if r.get("artistName", "").casefold() == track.artists[0].casefold()
        and (r.get("plainLyrics") or r.get("syncedLyrics"))
    ]
    if not candidates:
        candidates = [r for r in results if r.get("plainLyrics") or r.get("syncedLyrics")]
    if not candidates:
        return None
    best = min(
        candidates,
        key=lambda r: abs((r.get("duration") or duration) - duration),
    )
    plain = best.get("plainLyrics") or _strip_timestamps(best.get("syncedLyrics") or "")
    return plain.strip() or None
