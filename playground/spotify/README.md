# Spotify Library Indexer

Indexes the user's Spotify library via the Spotify Web API, fetches lyrics from [LRCLIB](https://lrclib.net), and stores embeddings in Qdrant.

Tracks are the unit of indexing. Each track becomes one Qdrant point: vector = compact header (artists + genres) + plain lyrics; payload = full metadata (album, year, popularity, playlists, genres, lyrics, Spotify URL). Lyrics are cached in the payloads — syncs fetch only tracks without lyrics and re-embed only tracks whose embedding text changed.

## Setup

1. Create an app at https://developer.spotify.com/dashboard (dev mode is fine, personal use)
   - Add redirect URI `http://localhost:8888/callback`
2. Create a `.env` file from the example:
   ```sh
   # Spotify app: create at https://developer.spotify.com/dashboard (dev mode is fine)
   # Add redirect URI http://localhost:8888/callback in the app settings
   SPOTIFY_CLIENT_ID=
   SPOTIFY_REDIRECT_URI=http://localhost:8888/callback

   # Same values as in mikoshi/.env
   LLAMACTL_API_BASE_URL=http://localhost:9001/v1
   LLAMACTL_API_KEY=
   EMBED_MODEL=Qwen3-Embedding-0.6B
   VECTOR_SIZE=1024

   QDRANT_URL=http://localhost:6333
   QDRANT_COLLECTION=spotify_tracks
```
3. `uv sync`

## Usage

```sh
# Authenticate with Spotify
uv run spotify-indexer auth

# Sync library: index new tracks, fetch lyrics, embed into Qdrant
uv run spotify-indexer sync  # --force to re-embed everything

# Index stats
uv run spotify-indexer status
```
