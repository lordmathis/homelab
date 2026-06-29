import io
import os
import tempfile
import wave

import httpx


def synthesize(
    text: str,
    language: str = "en",
    base_url: str = "http://localhost:9100",
) -> tuple[str, float]:
    """Synthesize speech via the audio service.

    Returns ``(temp_wav_path, duration_seconds)``. The caller is responsible
    for playing the file and removing it when done.
    """
    resp = httpx.post(
        f"{base_url}/v1/audio/speech",
        json={
            "model": "tts-1",
            "input": text,
            "language": language,
            "speed": 1.0,
        },
        timeout=60.0,
    )
    resp.raise_for_status()
    wav_bytes = resp.content

    with io.BytesIO(wav_bytes) as buf, wave.open(buf, "rb") as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
        duration = frames / rate if rate else 0.0

    fd, path = tempfile.mkstemp(suffix=".wav", prefix="tts_")
    with os.fdopen(fd, "wb") as f:
        f.write(wav_bytes)

    return path, duration
