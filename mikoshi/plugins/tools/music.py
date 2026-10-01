import logging
import os
from collections import Counter
from typing import Any, Dict, List, Optional

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

from mikoshi.tools.toolset_handler import ToolSetHandler, tool

logger = logging.getLogger(__name__)

QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
COLLECTION = os.environ.get("QDRANT_COLLECTION", "spotify_tracks")
EMBED_PROVIDER = os.environ.get("EMBED_PROVIDER", "llamactl")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "Qwen3-Embedding-0.6B")


class MusicTools(ToolSetHandler):
    """Semantic search over the user's indexed Spotify music library."""

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
            "artist, or any natural-language description (e.g. 'song about heartbreak "
            "with a hopeful ending', 'aggressive metal breakdowns', 'chill synthwave "
            "for driving'). Tracks are matched semantically against artist names and "
            "lyrics. Use artist= to restrict to one exact artist name, "
            "include_lyrics=true to also return the full lyrics."
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
                    "description": "Optional: exact artist name to restrict results to (e.g. 'Bad Omens').",
                },
                "include_lyrics": {
                    "type": "boolean",
                    "description": "Include full lyrics in results (default false).",
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
        limit: int = 10,
    ) -> Any:
        if not self._client:
            return "Error: music search not initialized."

        vec = await self._embed(query)
        if not vec:
            return "Error: failed to embed query (is the llamactl provider configured?)."

        must = []
        if artist:
            must.append(FieldCondition(key="artists", match=MatchValue(value=artist)))
        query_filter = Filter(must=must) if must else None

        try:
            response = await self._client.query_points(
                collection_name=COLLECTION,
                query=vec,
                query_filter=query_filter,
                limit=max(1, min(int(limit or 10), 50)),
            )
        except Exception as e:
            logger.error("MusicTools: qdrant search failed: %s", e, exc_info=True)
            return f"Error: failed to search music library: {e}"

        if not response.points:
            return {
                "results": [],
                "count": 0,
                "note": "no matches — is the library indexed? run spotify-indexer sync",
            }

        results = []
        for hit in response.points:
            p = hit.payload or {}
            item: Dict[str, Any] = {
                "name": p.get("name"),
                "artists": p.get("artists", []),
                "album": p.get("album"),
                "year": p.get("year"),
                "playlists": p.get("playlists", []),
                "saved": p.get("saved"),
                "spotify_url": p.get("spotify_url"),
                "score": hit.score,
            }
            if include_lyrics:
                item["lyrics"] = p.get("lyrics")
            results.append(item)
        return {"results": results, "count": len(results)}

    @tool(
        description=(
            "List the user's playlists that are present in the indexed music library, "
            "with track counts. Useful for discovering what the library contains "
            "before searching."
        ),
        parameters={"type": "object", "properties": {}, "required": []},
    )
    async def list_music_playlists(self) -> Any:
        if not self._client:
            return "Error: music search not initialized."

        counts: Counter = Counter()
        offset = None
        try:
            while True:
                points, offset = await self._client.scroll(
                    collection_name=COLLECTION,
                    limit=256,
                    offset=offset,
                    with_payload=["playlists"],
                    with_vectors=False,
                )
                for point in points:
                    for name in (point.payload or {}).get("playlists", []):
                        counts[name] += 1
                if offset is None:
                    break
        except Exception as e:
            logger.error("MusicTools: qdrant scroll failed: %s", e, exc_info=True)
            return f"Error: failed to list playlists: {e}"

        playlists = [{"name": name, "tracks": count} for name, count in counts.most_common()]
        return {"playlists": playlists, "count": len(playlists)}
