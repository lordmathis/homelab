import time

import httpx

from .config import Config

BATCH_SIZE = 32
RETRIES = 3


def embed_texts(cfg: Config, texts: list[str]) -> list[list[float]]:
    vectors: list[list[float]] = []
    with httpx.Client(timeout=120) as client:
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i : i + BATCH_SIZE]
            vectors.extend(_embed_batch(cfg, client, batch))
    return vectors


def _embed_batch(cfg: Config, client: httpx.Client, batch: list[str]) -> list[list[float]]:
    for attempt in range(RETRIES):
        try:
            resp = client.post(
                f"{cfg.llamactl_api_base_url.rstrip('/')}/embeddings",
                headers={"Authorization": f"Bearer {cfg.llamactl_api_key}"},
                json={"model": cfg.embed_model, "input": batch},
            )
            if resp.status_code in (429, 500, 502, 503):
                time.sleep(2**attempt * 2)
                continue
            resp.raise_for_status()
            data = resp.json()
            ordered = sorted(data["data"], key=lambda d: d["index"])
            return [item["embedding"] for item in ordered]
        except httpx.HTTPError:
            if attempt == RETRIES - 1:
                raise
            time.sleep(2**attempt * 2)
    raise RuntimeError("unreachable")
