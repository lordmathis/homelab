import uuid
from collections.abc import Iterator

from qdrant_client import QdrantClient, models

from .spotify import Track


def point_id(track_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"spotify:track:{track_id}"))


def client(qdrant_url: str) -> QdrantClient:
    return QdrantClient(url=qdrant_url, timeout=60)


def ensure_collection(c: QdrantClient, collection: str, vector_size: int) -> None:
    if not any(col.name == collection for col in c.get_collections().collections):
        c.create_collection(
            collection_name=collection,
            vectors_config=models.VectorParams(
                size=vector_size, distance=models.Distance.COSINE, on_disk=True
            ),
        )


def stored_payloads(c: QdrantClient, collection: str) -> dict[str, dict]:
    payloads: dict[str, dict] = {}
    for _, payload in _scroll_payloads(
        c, collection, ["track_id", "content_hash", "lyrics", "playcount", "last_played"]
    ):
        if payload.get("track_id"):
            payloads[payload["track_id"]] = payload
    return payloads


def all_point_ids(c: QdrantClient, collection: str) -> list[str]:
    return [pid for pid, _ in _scroll_payloads(c, collection, [])]


def _scroll_payloads(
    c: QdrantClient, collection: str, fields: list[str]
) -> Iterator[tuple[str | None, dict]]:
    offset = None
    while True:
        points, offset = c.scroll(
            collection_name=collection,
            limit=256,
            offset=offset,
            with_payload=fields or False,
            with_vectors=False,
        )
        for p in points:
            yield p.id, (p.payload or {})
        if offset is None:
            break


def payload_for(track: Track, content_hash: str) -> dict:
    return {
        "content_hash": content_hash,
        "track_id": track.id,
        "name": track.name,
        "artists": track.artists,
        "album": track.album,
        "year": track.year,
        "duration_s": track.duration_ms // 1000,
        "popularity": track.popularity,
        "playlists": track.playlists,
        "saved": track.saved,
        "lyrics": track.lyrics,
        "has_lyrics": track.lyrics is not None,
        "playcount": track.playcount,
        "last_played": track.last_played,
        "spotify_url": f"https://open.spotify.com/track/{track.id}",
    }


def upsert(
    c: QdrantClient, collection: str, records: list[tuple[Track, str]], vectors: list[list[float]]
) -> None:
    points = [
        models.PointStruct(
            id=point_id(track.id),
            vector=vector,
            payload=payload_for(track, content_hash),
        )
        for (track, content_hash), vector in zip(records, vectors, strict=True)
    ]
    for i in range(0, len(points), 100):
        c.upsert(collection_name=collection, points=points[i : i + 100])


def update_payloads(c: QdrantClient, collection: str, records: list[tuple[Track, str]]) -> None:
    for track, content_hash in records:
        c.set_payload(
            collection_name=collection,
            payload=payload_for(track, content_hash),
            points=[point_id(track.id)],
        )


def prune(c: QdrantClient, collection: str, keep_track_ids: set[str]) -> int:
    keep = {point_id(tid) for tid in keep_track_ids}
    stale = [pid for pid in all_point_ids(c, collection) if pid not in keep]
    for i in range(0, len(stale), 100):
        c.delete(collection_name=collection, points_selector=stale[i : i + 100])
    return len(stale)


def count(c: QdrantClient, collection: str) -> int:
    return c.count(collection_name=collection, exact=True).count


def count_with_lyrics(c: QdrantClient, collection: str) -> int:
    return c.count(
        collection_name=collection,
        exact=True,
        count_filter=models.Filter(
            must=[models.FieldCondition(key="has_lyrics", match=models.MatchValue(value=True))]
        ),
    ).count
