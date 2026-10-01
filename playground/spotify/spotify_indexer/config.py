import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).resolve().parents[1]

load_dotenv(PROJECT_DIR / ".env")


@dataclass
class Config:
    spotify_client_id: str | None
    spotify_redirect_uri: str
    llamactl_api_base_url: str | None
    llamactl_api_key: str | None
    qdrant_url: str
    qdrant_collection: str
    embed_model: str
    vector_size: int
    lyrics_min_interval: float

    @classmethod
    def load(cls) -> "Config":
        return cls(
            spotify_client_id=os.environ.get("SPOTIFY_CLIENT_ID"),
            spotify_redirect_uri=os.environ.get("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback"),
            llamactl_api_base_url=os.environ.get("LLAMACTL_API_BASE_URL"),
            llamactl_api_key=os.environ.get("LLAMACTL_API_KEY"),
            qdrant_url=os.environ.get("QDRANT_URL", "http://localhost:6333"),
            qdrant_collection=os.environ.get("QDRANT_COLLECTION", "spotify_tracks"),
            embed_model=os.environ.get("EMBED_MODEL", "Qwen3-Embedding-0.6B"),
            vector_size=int(os.environ.get("VECTOR_SIZE", "1024")),
            lyrics_min_interval=float(os.environ.get("LYRICS_MIN_INTERVAL", "1.0")),
        )

    def require_spotify(self) -> None:
        if not self.spotify_client_id:
            raise SystemExit("SPOTIFY_CLIENT_ID not set. Copy .env.example to .env and fill it in.")

    def require_llamactl(self) -> None:
        if not self.llamactl_api_base_url or not self.llamactl_api_key:
            raise SystemExit("LLAMACTL_API_BASE_URL / LLAMACTL_API_KEY not set (same values as mikoshi/.env).")
