import threading
import time
import numpy as np
import os

from edge_impulse_linux.audio import AudioImpulseRunner

MODEL_PATH = os.path.join(os.path.dirname(__file__), "models", "hey-reachy-wake-word-detection-mac-arm64.eim")


class WakeWordDetector:
    def __init__(self, reachy_mini, on_detected, threshold: float):
        self._reachy = reachy_mini
        self._on_detected = on_detected
        self._threshold = threshold
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._cooldown_until = 0.0

    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if (
            self._thread
            and self._thread.is_alive()
            and self._thread is not threading.current_thread()
        ):
            self._thread.join(timeout=2.0)

    def _run(self):
        print(f"[wake_word] Using model: {os.path.basename(MODEL_PATH)}")

        with AudioImpulseRunner(MODEL_PATH) as runner:
            model_info = runner.init()
            model_freq = model_info["model_parameters"]["frequency"]
            window_size = runner.window_size
            print(f"[wake_word] Model: {model_freq}Hz, window: {window_size} samples")

            resample_ratio = model_freq / 16000
            features = np.array([], dtype=np.int16)

            while not self._stop_event.is_set():
                sample = self._reachy.media.get_audio_sample()
                if sample is None:
                    time.sleep(0.01)
                    continue

                features = np.concatenate((features, self._to_int16(sample, resample_ratio)))
                features = self._classify(runner, features, window_size)

    def _to_int16(self, sample: np.ndarray, resample_ratio: float) -> np.ndarray:
        mono = sample.mean(axis=1)
        if resample_ratio != 1.0:
            new_length = int(len(mono) * resample_ratio)
            mono = np.interp(
                np.linspace(0, len(mono) - 1, new_length),
                np.arange(len(mono)),
                mono,
            )
        return (np.clip(mono, -1.0, 1.0) * 32767).astype(np.int16)

    def _classify(self, runner, features: np.ndarray, window_size: int) -> np.ndarray:
        while len(features) >= window_size:
            if self._stop_event.is_set():
                break
            res = runner.classify(features[:window_size].tolist())
            features = features[int(window_size * 0.25):]

            classification = res["result"].get("classification")
            if not classification:
                continue

            score = classification.get("hey_reachy", 0)
            if score <= self._threshold:
                continue

            now = time.time()
            if now < self._cooldown_until:
                continue

            self._cooldown_until = now + 3.0
            print(f"[wake_word] Detected! score={score:.4f}")
            self._on_detected()

        return features
