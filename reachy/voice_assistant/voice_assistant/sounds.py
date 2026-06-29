import math
import os
import tempfile
import wave

import numpy as np

CUE_FILENAME = "reachy_listening_cue.wav"
CUE_PATH = os.path.join(tempfile.gettempdir(), CUE_FILENAME)


def _write_wav(path: str, samples: np.ndarray, sample_rate: int = 16000) -> None:
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())


def ensure_listening_cue(path: str = CUE_PATH) -> str:
    """Generate a short rising two-tone 'listening' blip once.

    Returns a stable WAV path. Using a fixed filename means the daemon caches
    the upload after the first turn instead of re-uploading each time.
    """
    if os.path.exists(path):
        return path

    sample_rate = 16000
    seg = 0.06
    n = int(sample_rate * seg)
    t = np.arange(n) / sample_rate

    def envelope(time: np.ndarray) -> np.ndarray:
        attack = 0.008
        return np.minimum(time / attack, 1.0) * np.exp(-time * 18.0)

    low = 0.5 * envelope(t) * np.sin(2 * math.pi * 740.0 * t)
    high = 0.5 * envelope(t) * np.sin(2 * math.pi * 990.0 * t)
    cue = np.concatenate([low, high])

    _write_wav(path, cue, sample_rate)
    return path
