from dataclasses import dataclass, field

import spotipy
from spotipy.cache_handler import CacheFileHandler
from spotipy.oauth2 import SpotifyPKCE

from .config import Config, PROJECT_DIR

SCOPES = "user-library-read playlist-read-private playlist-read-collaborative"


@dataclass
class Track:
    id: str
    name: str
    artists: list[str]
    artist_ids: list[str]
    album: str
    year: str | None
    duration_ms: int
    popularity: int
    saved: bool = False
    playlists: list[str] = field(default_factory=list)
    genres: list[str] = field(default_factory=list)
    lyrics: str | None = None


def client(cfg: Config) -> spotipy.Spotify:
    auth = SpotifyPKCE(
        client_id=cfg.spotify_client_id,
        redirect_uri=cfg.spotify_redirect_uri,
        scope=SCOPES,
        cache_handler=CacheFileHandler(cache_path=str(PROJECT_DIR / ".cache")),
        open_browser=True,
    )
    return spotipy.Spotify(auth_manager=auth)


def _paginate(sp: spotipy.Spotify, first_page: dict):
    page = first_page
    while page:
        yield page
        page = sp.next(page) if page.get("next") else None


def harvest(sp: spotipy.Spotify) -> dict[str, Track]:
    tracks: dict[str, Track] = {}

    def add(t: dict, album: str | None = None, year: str | None = None, saved: bool = False, playlist: str | None = None) -> None:
        if not t or t.get("is_local") or not t.get("id") or t.get("type", "track") != "track":
            return
        existing = tracks.get(t["id"])
        if existing:
            existing.saved = existing.saved or saved
            if playlist and playlist not in existing.playlists:
                existing.playlists.append(playlist)
            return
        release_date = (t.get("album") or {}).get("release_date") or ""
        tracks[t["id"]] = Track(
            id=t["id"],
            name=t["name"],
            artists=[a["name"] for a in t["artists"]],
            artist_ids=[a["id"] for a in t["artists"]],
            album=album or (t.get("album") or {}).get("name", ""),
            year=year or release_date[:4] or None,
            duration_ms=t["duration_ms"],
            popularity=t.get("popularity", 0),
            saved=saved,
            playlists=[playlist] if playlist else [],
        )

    for page in _paginate(sp, sp.current_user_saved_tracks(limit=50)):
        for item in page["items"]:
            add(item["track"], saved=True)

    for page in _paginate(sp, sp.current_user_saved_albums(limit=50)):
        for item in page["items"]:
            album = item["album"]
            year = album.get("release_date", "")[:4] or None
            for t in album["tracks"]["items"]:
                add(t, album=album["name"], year=year, saved=True)

    for page in _paginate(sp, sp.current_user_playlists(limit=50)):
        for pl in page["items"]:
            for pl_page in _paginate(sp, sp.playlist_items(pl["id"], limit=100)):
                for item in pl_page["items"]:
                    add(item.get("track"), playlist=pl["name"])

    genre_map = _artist_genres(sp, {aid for t in tracks.values() for aid in t.artist_ids})
    for track in tracks.values():
        genres: list[str] = []
        for aid in track.artist_ids:
            for g in genre_map.get(aid, []):
                if g not in genres:
                    genres.append(g)
        track.genres = genres[:6]

    return tracks


def _artist_genres(sp: spotipy.Spotify, artist_ids: set[str]) -> dict[str, list[str]]:
    genres: dict[str, list[str]] = {}
    ids = sorted(artist_ids)
    for i in range(0, len(ids), 50):
        resp = sp.artists(ids[i : i + 50])
        for artist in resp["artists"]:
            genres[artist["id"]] = artist.get("genres", [])
    return genres
