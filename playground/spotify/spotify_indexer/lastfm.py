import json
import time
from collections import defaultdict
from dataclasses import dataclass, field

import httpx

from .config import Config, PROJECT_DIR
from .lyrics import RateLimiter
from .spotify import Track

LASTFM_BASE = "https://ws.audioscrobbler.com/2.0/"
RETRIES = 3
STATE_FILE = PROJECT_DIR / "lastfm_state.json"


@dataclass
class ScrobbleAgg:
    total: int = 0
    last_played: int = 0
    by_month: dict[str, int] = field(default_factory=dict)


def month_key(uts: int) -> str:
    return time.strftime("%Y-%m", time.gmtime(uts))

_client: httpx.Client | None = None
_limiter: RateLimiter | None = None


def init(cfg: Config) -> None:
    global _client, _limiter
    _client = httpx.Client(timeout=30)
    _limiter = RateLimiter(min_interval=0.25)


def _norm(text: str) -> str:
    return " ".join(text.casefold().split())


def key_for(track: Track) -> tuple[str, str]:
    return _norm(track.artists[0]), _norm(track.name)


def _request(params: dict) -> dict | None:
    for attempt in range(RETRIES):
        try:
            _limiter.acquire()
            resp = _client.get(LASTFM_BASE, params=params)
            if resp.status_code in (429, 500, 502, 503):
                time.sleep(2**attempt * 2)
                continue
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError:
            if attempt == RETRIES - 1:
                return None
            time.sleep(2**attempt * 2)
    return None


def _load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def _save_state(last_sync: int) -> None:
    STATE_FILE.write_text(json.dumps({"last_sync": last_sync}))


def fetch_history(cfg: Config) -> tuple[dict[tuple[str, str], ScrobbleAgg], bool]:
    """Fetch scrobbles since the last sync. Returns ((artist, title) -> ScrobbleAgg, is_full_backfill)."""
    since = _load_state().get("last_sync")
    fetch_started = int(time.time())

    agg: dict[tuple[str, str], ScrobbleAgg] = defaultdict(ScrobbleAgg)
    page = 1
    total_pages = 1
    while page <= total_pages:
        data = _request(
            {
                "method": "user.getrecenttracks",
                "user": cfg.lastfm_user,
                "api_key": cfg.lastfm_api_key,
                "format": "json",
                "limit": 200,
                "page": page,
                "from": since,
            }
        )
        if data is None:
            raise RuntimeError(f"Last.fm request failed on page {page}")
        recent = data.get("recenttracks", {})
        total_pages = int(recent.get("@attr", {}).get("totalPages", 1))
        for t in recent.get("track", []):
            if t.get("nowplaying") or "date" not in t:
                continue
            uts = int(t["date"]["uts"])
            key = (_norm(t["artist"]["#text"]), _norm(t["name"]))
            entry = agg[key]
            entry.total += 1
            entry.last_played = max(entry.last_played, uts)
            month = month_key(uts)
            entry.by_month[month] = entry.by_month.get(month, 0) + 1
        if page % 10 == 0 or page == total_pages:
            print(f"    scrobbles: page {page}/{total_pages}")
        page += 1

    _save_state(fetch_started)
    return dict(agg), since is None


def apply_history(
    tracks: dict[str, Track], history: dict[tuple[str, str], ScrobbleAgg], full: bool
) -> int:
    matched = 0
    for track in tracks.values():
        entry = history.get(key_for(track))
        if entry is None:
            if full:
                track.playcount = 0
                track.playcount_by_month = {}
            continue
        track.playcount = entry.total if full else track.playcount + entry.total
        track.last_played = max(track.last_played or 0, entry.last_played) or None
        if full:
            track.playcount_by_month = dict(entry.by_month)
        else:
            for month, count in entry.by_month.items():
                track.playcount_by_month[month] = track.playcount_by_month.get(month, 0) + count
        matched += 1
    return matched
