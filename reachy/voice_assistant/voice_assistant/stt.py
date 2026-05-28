import io
import struct

import httpx
import numpy as np


def audio_to_wav(mono_pcm16: np.ndarray, sample_rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    data = mono_pcm16.tobytes()
    data_size = len(data)
    buf.write(b"RIFF")
    buf.write(struct.pack("<I", 36 + data_size))
    buf.write(b"WAVE")
    buf.write(b"fmt ")
    buf.write(struct.pack("<I", 16))
    buf.write(
        struct.pack("<HHIIHH", 1, 1, sample_rate, sample_rate * 2, 2, 16)
    )
    buf.write(b"data")
    buf.write(struct.pack("<I", data_size))
    buf.write(data)
    return buf.getvalue()


def transcribe(
    audio: np.ndarray,
    sample_rate: int = 16000,
    base_url: str = "http://localhost:9100",
) -> str:
    mono = audio.mean(axis=1) if audio.ndim > 1 else audio
    pcm16 = (np.clip(mono, -1.0, 1.0) * 32767).astype(np.int16)
    wav_bytes = audio_to_wav(pcm16, sample_rate)

    resp = httpx.post(
        f"{base_url}/v1/audio/transcriptions",
        files={"file": ("audio.wav", wav_bytes, "audio/wav")},
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()["text"].strip()
