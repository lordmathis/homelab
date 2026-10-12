import logging
import math
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchText, Range

from mikoshi.tools.toolset_handler import ToolSetHandler, tool

logger = logging.getLogger(__name__)

QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
COLLECTION = os.environ.get("QDRANT_COLLECTION", "spotify_tracks")
EMBED_PROVIDER = os.environ.get("EMBED_PROVIDER", "llamactl")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "Qwen3-Embedding-0.6B")

OVERFETCH = 100
RECENCY_HALF_LIFE_S = 90 * 24 * 3600
FAMILIARITY_SATURATION = 50
MAX_SCROLL = 5000
SORT_KEYS = ("playcount", "last_played", "year", "name")
GROUP_KEYS = ("album", "artist")
NO_MATCH_NOTE = "no matches — is the library indexed? run spotify-indexer sync"


def _adjusted_score(score: float, payload: Dict[str, Any], recency_bias: float) -> float:
    last_played = payload.get("last_played") or 0
    playcount = payload.get("playcount") or 0
    recency = math.exp(-(time.time() - last_played) / RECENCY_HALF_LIFE_S) if last_played else 0.0
    familiarity = min(playcount / FAMILIARITY_SATURATION, 1.0)
    return score * (1 + recency_bias * (0.7 * recency + 0.3 * familiarity))


def _period_months(period: str, now: Optional[datetime] = None) -> Optional[List[str]]:
    """Parse 'YYYY', 'YYYY-MM', or 'Nm' (trailing N months incl. current) into 'YYYY-MM' keys."""
    if now is None:
        now = datetime.now(timezone.utc)

    m = re.fullmatch(r"(\d{4})(?:-(\d{2}))?", period)
    if m:
        year, month = m.group(1), m.group(2)
        if month is not None:
            return [f"{year}-{month}"] if 1 <= int(month) <= 12 else None
        return [f"{year}-{mm:02d}" for mm in range(1, 13)]

    m = re.fullmatch(r"(\d{1,2})m", period)
    if m:
        n = int(m.group(1))
        if n < 1:
            return None
        months = []
        year, month = now.year, now.month
        for _ in range(n):
            months.append(f"{year:04d}-{month:02d}")
            month -= 1
            if month == 0:
                year, month = year - 1, 12
        return months

    return None


def _plays_in_period(payload: Dict[str, Any], months: List[str]) -> int:
    buckets = payload.get("playcount_by_month") or {}
    return sum(buckets.get(m, 0) for m in months)


def _track_item(
    payload: Dict[str, Any],
    months: Optional[List[str]] = None,
    include_lyrics: bool = False,
    score: Optional[float] = None,
) -> Dict[str, Any]:
    item: Dict[str, Any] = {
        "name": payload.get("name"),
        "artists": payload.get("artists", []),
        "album": payload.get("album"),
        "year": payload.get("year"),
        "playlists": payload.get("playlists", []),
        "popularity": payload.get("popularity", 0),
        "playcount": payload.get("playcount", 0),
        "last_played": payload.get("last_played"),
        "spotify_url": payload.get("spotify_url"),
    }
    if score is not None:
        item["score"] = score
    if include_lyrics:
        item["lyrics"] = payload.get("lyrics")
    if months is not None:
        item["plays_in_period"] = _plays_in_period(payload, months)
    return item


def _drop_zero_period(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [it for it in items if (it.get("plays_in_period") or 0) > 0]


def _sorted_items(items: List[Dict[str, Any]], sort_key: str) -> List[Dict[str, Any]]:
    if sort_key == "name":
        return sorted(items, key=lambda it: (it.get("name") or "").casefold())
    return sorted(items, key=lambda it: it.get(sort_key) or 0, reverse=True)


def _aggregate(tracks: List[Dict[str, Any]], sort_key: str) -> float:
    if sort_key == "name":
        return float(len(tracks))
    if sort_key in ("playcount", "plays_in_period"):
        return float(sum(t.get(sort_key) or 0 for t in tracks))
    return float(max((t.get(sort_key) or 0 for t in tracks), default=0))


def _distinct_artists(tracks: List[Dict[str, Any]]) -> List[str]:
    seen = set()
    out = []
    for t in tracks:
        for a in t.get("artists") or []:
            if a not in seen:
                seen.add(a)
                out.append(a)
    return out


def _group_tracks(items: List[Dict[str, Any]], group_by: str, sort_key: str) -> List[Dict[str, Any]]:
    members: Dict[str, List[Dict[str, Any]]] = {}
    for item in items:
        keys = [item.get("album") or ""] if group_by == "album" else (item.get("artists") or [])
        for key in keys:
            members.setdefault(key, []).append(item)

    ranked: List[Tuple[float, Dict[str, Any]]] = []
    for name, tracks in members.items():
        years = [t["year"] for t in tracks if t.get("year")]
        group: Dict[str, Any] = {
            "name": name,
            "artists": _distinct_artists(tracks)[:5],
            "year": max(years) if years else None,
            "track_count": len(tracks),
            "playcount": sum(t.get("playcount") or 0 for t in tracks),
            "top_tracks": tracks[:3],
        }
        if sort_key == "plays_in_period":
            group["plays_in_period"] = sum(t.get("plays_in_period") or 0 for t in tracks)
        ranked.append((_aggregate(tracks, sort_key), group))
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return [group for _, group in ranked]


def _grouped_response(items: List[Dict[str, Any]], group_by: str, sort_key: str, limit: int) -> Dict[str, Any]:
    groups = _group_tracks(items, group_by, sort_key)[:limit]
    return {"groups": groups, "count": len(groups)}


def _build_filter(
    artist: Optional[str] = None,
    album: Optional[str] = None,
    word: Optional[str] = None,
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
) -> Optional[Filter]:
    must: List[Any] = []
    if artist:
        must.append(FieldCondition(key="artists", match=MatchText(text=artist)))
    if album:
        must.append(FieldCondition(key="album", match=MatchText(text=album)))
    if word:
        must.append(
            Filter(
                should=[
                    FieldCondition(key="name", match=MatchText(text=word)),
                    FieldCondition(key="album", match=MatchText(text=word)),
                    FieldCondition(key="lyrics", match=MatchText(text=word)),
                ]
            )
        )
    if year_min is not None or year_max is not None:
        must.append(FieldCondition(key="year", range=Range(gte=year_min, lte=year_max)))
    return Filter(must=must) if must else None


def _projection(include_lyrics: bool, months: Optional[List[str]]) -> List[str]:
    fields = [
        "name",
        "artists",
        "album",
        "year",
        "playlists",
        "popularity",
        "playcount",
        "last_played",
        "spotify_url",
    ]
    if include_lyrics:
        fields.append("lyrics")
    if months is not None:
        fields.append("playcount_by_month")
    return fields


class MusicTools(ToolSetHandler):
    """Semantic search and structured browsing over the user's indexed Spotify music library."""

    server_name = "music"

    def __init__(self):
        super().__init__()
        self._client: Optional[AsyncQdrantClient] = None

    async def initialize(self):
        await super().initialize()
        self._client = AsyncQdrantClient(url=QDRANT_URL)
        logger.info(
            "MusicTools ready: qdrant=%s collection=%s embed=%s/%s",
            QDRANT_URL,
            COLLECTION,
            EMBED_PROVIDER,
            EMBED_MODEL,
        )

    async def cleanup(self):
        if self._client:
            await self._client.close()

    async def _embed(self, text: str) -> Optional[List[float]]:
        if not self._tool_manager:
            logger.error("MusicTools: tool manager not set, cannot resolve provider")
            return None
        provider = self._tool_manager.get_provider(EMBED_PROVIDER)
        if provider is None:
            logger.error("MusicTools: embed provider '%s' not found", EMBED_PROVIDER)
            return None
        try:
            return await provider.get_llm_client().create_embedding(EMBED_MODEL, text)
        except Exception as e:
            logger.error("MusicTools: embedding request failed: %s", e, exc_info=True)
            return None

    @tool(
        description=(
            "Search the user's Spotify music library by meaning: lyrical themes, mood, "
            "or any natural-language description (e.g. 'song about heartbreak with a "
            "hopeful ending', 'aggressive metal breakdowns', 'chill synthwave for "
            "driving'). Tracks are matched semantically against artist names and "
            "lyrics, then boosted by listening recency and frequency (set "
            "recency_bias=0 for pure semantic ranking). Use artist= to restrict to "
            "one artist. For questions about facts — release years, albums, most "
            "played, words in titles — use browse_music instead."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural-language description of what to find.",
                },
                "artist": {
                    "type": "string",
                    "description": "Optional: artist name to restrict results to (whole words, case-insensitive).",
                },
                "include_lyrics": {
                    "type": "boolean",
                    "description": "Include full lyrics in results (default false).",
                },
                "recency_bias": {
                    "type": "number",
                    "description": "How strongly to boost recently/frequently played tracks. 0 disables (pure semantic), default 1.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max number of results (default 10, max 50).",
                },
            },
            "required": ["query"],
        },
    )
    async def search_music(
        self,
        query: str,
        artist: Optional[str] = None,
        include_lyrics: bool = False,
        recency_bias: float = 1.0,
        limit: int = 10,
    ) -> Any:
        if not self._client:
            return "Error: music search not initialized."

        vec = await self._embed(query)
        if not vec:
            return "Error: failed to embed query (is the llamactl provider configured?)."

        limit = max(1, min(int(limit or 10), 50))
        fetch_n = limit if recency_bias <= 0 else max(limit, OVERFETCH)

        try:
            response = await self._client.query_points(
                collection_name=COLLECTION,
                query=vec,
                query_filter=_build_filter(artist=artist),
                limit=fetch_n,
                with_payload=_projection(include_lyrics, None),
            )
        except Exception as e:
            logger.error("MusicTools: qdrant search failed: %s", e, exc_info=True)
            return f"Error: failed to search music library: {e}"

        pairs: List[Tuple[Dict[str, Any], float]] = []
        for hit in response.points:
            payload = hit.payload or {}
            item = _track_item(payload, include_lyrics=include_lyrics, score=hit.score)
            rank = _adjusted_score(hit.score, payload, recency_bias) if recency_bias > 0 else hit.score
            pairs.append((item, rank))

        pairs.sort(key=lambda pair: pair[1], reverse=True)
        results = [item for item, _ in pairs[:limit]]
        if not results:
            return {"results": [], "count": 0, "note": NO_MATCH_NOTE}
        return {"results": results, "count": len(results)}

    @tool(
        description=(
            "Browse the user's Spotify music library by facts: release year, artist, "
            "album, words, and listening history. Examples: albums released in 2026 "
            "(year_min=2026, group_by='album'); tracks most played this year "
            "(period='2026', or period='6m' for the last 6 months); tracks with "
            "'fire' in the name or lyrics (word='fire'); one artist's catalog "
            "(artist='...', group_by='album'). All filters combine. word matches "
            "whole words (case-insensitive), not substrings. For meaning-based "
            "queries (themes, mood, lyrics about something) use search_music."
        ),
        parameters={
            "type": "object",
            "properties": {
                "artist": {
                    "type": "string",
                    "description": "Filter by artist name (whole words, case-insensitive).",
                },
                "album": {
                    "type": "string",
                    "description": "Filter by album name (whole words, case-insensitive).",
                },
                "word": {
                    "type": "string",
                    "description": "Tracks whose name, album, or lyrics contain this word.",
                },
                "year_min": {
                    "type": "integer",
                    "description": "Inclusive minimum release year.",
                },
                "year_max": {
                    "type": "integer",
                    "description": "Inclusive maximum release year.",
                },
                "period": {
                    "type": "string",
                    "description": (
                        "Listening window: 'YYYY', 'YYYY-MM', or 'Nm' (trailing N months "
                        "incl. current, e.g. '6m'). Restricts to tracks played in the window "
                        "and adds plays_in_period to results."
                    ),
                },
                "sort_by": {
                    "type": "string",
                    "description": (
                        "playcount | last_played | year | name. Default: period plays if "
                        "period given, else playcount. Descending except name (ascending)."
                    ),
                },
                "group_by": {
                    "type": "string",
                    "description": "album | artist — aggregate results into groups with top tracks.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max number of results or groups (default 10, max 50).",
                },
            },
            "required": [],
        },
    )
    async def browse_music(
        self,
        artist: Optional[str] = None,
        album: Optional[str] = None,
        word: Optional[str] = None,
        year_min: Optional[int] = None,
        year_max: Optional[int] = None,
        period: Optional[str] = None,
        sort_by: Optional[str] = None,
        group_by: Optional[str] = None,
        limit: int = 10,
    ) -> Any:
        if not self._client:
            return "Error: music search not initialized."

        months = None
        if period is not None:
            months = _period_months(period)
            if months is None:
                return (
                    f"Error: invalid period '{period}'. Use 'YYYY' (e.g. '2026'), 'YYYY-MM' "
                    "(e.g. '2026-03'), or 'Nm' for the trailing N months including the "
                    "current one (e.g. '6m')."
                )
        if sort_by is not None and sort_by not in SORT_KEYS:
            return f"Error: invalid sort_by '{sort_by}'. Accepted values: {', '.join(SORT_KEYS)}."
        if group_by is not None and group_by not in GROUP_KEYS:
            return f"Error: invalid group_by '{group_by}'. Accepted values: {', '.join(GROUP_KEYS)}."

        limit = max(1, min(int(limit or 10), 50))
        query_filter = _build_filter(
            artist=artist,
            album=album,
            word=word,
            year_min=year_min,
            year_max=year_max,
        )

        items: List[Dict[str, Any]] = []
        offset = None
        truncated = False
        try:
            while True:
                points, offset = await self._client.scroll(
                    collection_name=COLLECTION,
                    scroll_filter=query_filter,
                    limit=256,
                    offset=offset,
                    with_payload=_projection(False, months),
                    with_vectors=False,
                )
                items.extend(_track_item(p.payload or {}, months=months) for p in points)
                if offset is None:
                    break
                if len(items) >= MAX_SCROLL:
                    truncated = True
                    break
        except Exception as e:
            logger.error("MusicTools: qdrant scroll failed: %s", e, exc_info=True)
            return f"Error: failed to browse music library: {e}"

        if months is not None:
            items = _drop_zero_period(items)
        sort_key = sort_by or ("plays_in_period" if months is not None else "playcount")
        items = _sorted_items(items, sort_key)

        if group_by is not None:
            response = _grouped_response(items, group_by, sort_key, limit)
        else:
            results = items[:limit]
            response = {"results": results, "count": len(results)}
            if not results:
                response["note"] = NO_MATCH_NOTE
        if truncated:
            response["note"] = f"hit {MAX_SCROLL}-point scroll cap; results computed on a truncated set"

        logger.info(
            "MusicTools: browse filters=%s period=%s sort=%s group=%s returned=%s",
            [k for k, v in (("artist", artist), ("album", album), ("word", word)) if v]
            + (["year"] if year_min is not None or year_max is not None else []),
            period,
            sort_key,
            group_by,
            response.get("count") if isinstance(response, dict) else "error",
        )
        return response
