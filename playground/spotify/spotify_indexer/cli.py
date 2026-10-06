import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed

import typer

from . import embed, lastfm, lyrics, spotify, store
from .config import Config, PROJECT_DIR

app = typer.Typer(no_args_is_help=True)


def embedding_text(track: spotify.Track) -> str:
    header = ", ".join(track.artists)
    if track.lyrics:
        return f"{header}\nLyrics:\n{track.lyrics}"
    return header


def content_hash(track: spotify.Track) -> str:
    return hashlib.sha256(embedding_text(track).encode()).hexdigest()


@app.command()
def auth() -> None:
    """Authenticate with Spotify and verify the token works."""
    cfg = Config.load()
    cfg.require_spotify()
    me = spotify.client(cfg).me()
    typer.echo(f"Authenticated as {me['display_name']} ({me['id']}). Token cached in {PROJECT_DIR / '.cache'}")


@app.command()
def sync(
    force: bool = typer.Option(False, "--force", help="Re-embed everything, ignoring stored hashes."),
    limit: int = typer.Option(None, "--limit", help="Only index the first N tracks (for testing)."),
) -> None:
    """Harvest library, fetch lyrics, and index into Qdrant."""
    cfg = Config.load()
    cfg.require_spotify()
    cfg.require_llamactl()

    sp = spotify.client(cfg)
    typer.echo("Harvesting library from Spotify...")
    tracks = spotify.harvest(sp)
    if limit is not None:
        typer.echo(f"Found {len(tracks)} unique tracks, limiting to {limit}")
        tracks = dict(list(tracks.items())[:limit])
    else:
        typer.echo(f"Found {len(tracks)} unique tracks")

    qdrant = store.client(cfg.qdrant_url)
    store.ensure_collection(qdrant, cfg.qdrant_collection, cfg.vector_size)
    stored = store.stored_payloads(qdrant, cfg.qdrant_collection)
    for track in tracks.values():
        existing = stored.get(track.id)
        if existing:
            track.lyrics = existing.get("lyrics")
            track.playcount = existing.get("playcount") or 0
            track.last_played = existing.get("last_played")

    typer.echo("Fetching lyrics from LRCLIB...")
    lyrics.init(cfg)
    uncached = [t for t in tracks.values() if t.lyrics is None]
    if not uncached:
        typer.echo("  all lyrics already cached")
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(lyrics.fetch_lyrics, t): t for t in uncached}
        done = 0
        for future in as_completed(futures):
            track = futures[future]
            track.lyrics = future.result()
            done += 1
            status = f"{len(track.lyrics)} chars" if track.lyrics else "no match"
            typer.echo(f"  lyrics {done}/{len(uncached)}: {', '.join(track.artists)} - {track.name} ({status})")

    if cfg.lastfm_api_key and cfg.lastfm_user:
        typer.echo("Fetching listening history from Last.fm...")
        lastfm.init(cfg)
        history, full = lastfm.fetch_history(cfg)
        matched = lastfm.apply_history(tracks, history, full)
        typer.echo(f"  matched {matched}/{len(tracks)} tracks to scrobbles ({'full backfill' if full else 'incremental'})")
    else:
        typer.echo("Skipping Last.fm history (LASTFM_API_KEY / LASTFM_USER not set)")

    records = [(track, content_hash(track)) for track in tracks.values()]
    if force:
        changed, unchanged = records, []
    else:
        changed = [(t, h) for t, h in records if stored.get(t.id, {}).get("content_hash") != h]
        unchanged = [(t, h) for t, h in records if stored.get(t.id, {}).get("content_hash") == h]

    typer.echo(f"Embedding {len(changed)} tracks ({len(unchanged)} unchanged)...")
    if changed:
        vectors = embed.embed_texts(cfg, [embedding_text(t) for t, _ in changed])
        typer.echo(f"Upserting {len(changed)} points into '{cfg.qdrant_collection}'...")
        store.upsert(qdrant, cfg.qdrant_collection, changed, vectors)
    if unchanged:
        typer.echo(f"Refreshing payloads for {len(unchanged)} unchanged tracks...")
        store.update_payloads(qdrant, cfg.qdrant_collection, unchanged)

    if limit is not None:
        typer.echo("Skipping prune (--limit set)")
        pruned = 0
    else:
        typer.echo("Pruning stale points...")
        pruned = store.prune(qdrant, cfg.qdrant_collection, set(tracks.keys()))
    with_lyrics = sum(1 for t in tracks.values() if t.lyrics)
    typer.echo(
        f"Done: {len(tracks)} tracks indexed ({with_lyrics} with lyrics, "
        f"{len(changed)} embedded, {pruned} pruned)"
    )


@app.command()
def status() -> None:
    """Show index stats."""
    cfg = Config.load()
    try:
        qdrant = store.client(cfg.qdrant_url)
        try:
            points = store.count(qdrant, cfg.qdrant_collection)
            with_lyrics = store.count_with_lyrics(qdrant, cfg.qdrant_collection)
            typer.echo(f"Qdrant [{cfg.qdrant_url}] collection '{cfg.qdrant_collection}': {points} points ({with_lyrics} with lyrics)")
        except Exception:
            typer.echo(f"Qdrant [{cfg.qdrant_url}] reachable, collection '{cfg.qdrant_collection}' not created yet — run sync")
    except Exception as exc:
        typer.echo(f"Qdrant unreachable at {cfg.qdrant_url}: {exc}")


def main() -> None:
    app()
