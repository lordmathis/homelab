from dataclasses import dataclass, field

import spotipy
from spotipy.cache_handler import CacheFileHandler
from spotipy.oauth2 import SpotifyPKCE

from .config import Config, PROJECT_DIR

SCOPES = "user-library-read playlist-read-private"


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

    print("  Harvesting liked songs...")
    for page in _paginate(sp, sp.current_user_saved_tracks(limit=50)):
        for item in page["items"]:
            add(item["track"], saved=True)
    print(f"    liked songs: {len(tracks)} tracks")

    print("  Harvesting saved albums...")
    album_count = 0
    before = len(tracks)
    for page in _paginate(sp, sp.current_user_saved_albums(limit=50)):
        for item in page["items"]:
            album_count += 1
            album = item["album"]
            year = album.get("release_date", "")[:4] or None
            for t in album["tracks"]["items"]:
                add(t, album=album["name"], year=year, saved=True)
    print(f"    saved albums: {album_count} albums ({len(tracks) - before} new tracks)")

    print("  Harvesting playlists...")
    me = sp.me()["id"]
    for page in _paginate(sp, sp.current_user_playlists(limit=50)):
        for pl in page["items"]:
            if pl["owner"]["id"] != me:
                continue
            before = len(tracks)
            try:
                for pl_page in _paginate(sp, sp.playlist_items(pl["id"], limit=100)):
                    for item in pl_page["items"]:
                        add(item.get("track") or item.get("item"), playlist=pl["name"])
            except spotipy.SpotifyException as e:
                print(f"    Skipping inaccessible playlist '{pl['name']}' ({e.http_status})")
                continue
            print(f"    playlist '{pl['name']}': {len(tracks) - before} new tracks")

    return tracks
