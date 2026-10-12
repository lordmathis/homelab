# Spotify Library Indexer

Indexes the user's Spotify library via the Spotify Web API, fetches lyrics from [LRCLIB](https://lrclib.net), and stores embeddings in Qdrant.

Tracks are the unit of indexing. Each track becomes one Qdrant point: vector = artist names + plain lyrics; payload = full metadata (album, release `year` as int, popularity, monthly play counts, lyrics, Spotify URL). Lyrics are cached in the payloads — syncs fetch only tracks without lyrics and re-embed only tracks whose embedding text changed.

Payload fields of note:

- `year` — release year as an **integer** (payload index: integer).
- `playcount_by_month` — `"YYYY-MM"` (UTC calendar month) → play count buckets from Last.fm, summed over the track's lifetime. Merged incrementally on each sync; replaced wholesale on a full backfill.
- `name`, `album`, `lyrics`, `artists` — word-tokenizer text indexes for token matching; `year` integer index for range filters. Created idempotently at the end of every sync.

### One-time migration (done once, 2026)

Monthly history for past years lives only on Last.fm's servers — `lastfm_state.json` tracks just the last sync timestamp. To backfill the monthly buckets: delete `lastfm_state.json` once, then run `sync`; a full scrobble backfill (~1–2 min rate-limited) replaces all buckets and rewrites `year` as int. Incremental merges resume forever after.

## Setup

1. Create a `.env` file from the example:
   ```sh
   # Spotify app: create at https://developer.spotify.com/dashboard
   SPOTIFY_CLIENT_ID=
   SPOTIFY_REDIRECT_URI=http://127.0.0.1:8888/callback

   # Same values as in mikoshi/.env
   LLAMACTL_API_BASE_URL=http://localhost:9001/v1
   LLAMACTL_API_KEY=
   EMBED_MODEL=Qwen3-Embedding-0.6B
   VECTOR_SIZE=1024

   QDRANT_URL=http://localhost:6333
   QDRANT_COLLECTION=spotify_tracks

   # Optional: Last.fm listening history (https://www.last.fm/api/account/create)
   LASTFM_API_KEY=
   LASTFM_USER=
```
2. `uv sync`

## Usage

```sh
# Authenticate with Spotify
uv run spotify-indexer auth

# Sync library: index new tracks, fetch lyrics, embed into Qdrant
uv run spotify-indexer sync  # --force to re-embed everything, --limit N to index only the first N tracks

# Index stats
uv run spotify-indexer status
```
