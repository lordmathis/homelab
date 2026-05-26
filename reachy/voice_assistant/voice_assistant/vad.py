import numpy as np


class VoiceActivityDetector:
    def __init__(
        self,
        energy_threshold: float,
        end_of_utterance_silence: float,
        conversation_timeout: float,
        min_speech_duration: float,
        sample_rate: int = 16000,
    ):
        self.energy_threshold = energy_threshold
        self.end_of_utterance_silence = end_of_utterance_silence
        self.conversation_timeout = conversation_timeout
        self.min_speech_duration = min_speech_duration
        self.sample_rate = sample_rate

        self._speech_frames = 0
        self._silence_frames = 0
        self._total_silence_frames = 0
        self._has_speech = False

    def reset(self):
        self._speech_frames = 0
        self._silence_frames = 0
        self._total_silence_frames = 0
        self._has_speech = False

    def process_frame(self, audio: np.ndarray) -> dict:
        mono = audio.mean(axis=1) if audio.ndim > 1 else audio
        rms = np.sqrt(np.mean(mono ** 2))
        frame_samples = len(mono)
        is_speech = rms > self.energy_threshold

        if is_speech:
            self._speech_frames += frame_samples
            self._silence_frames = 0
            self._total_silence_frames = 0
            self._has_speech = True
        else:
            self._silence_frames += frame_samples
            if self._has_speech:
                self._total_silence_frames += frame_samples

        min_speech_samples = int(self.min_speech_duration * self.sample_rate)
        has_min_speech = self._speech_frames >= min_speech_samples

        silence_seconds = self._silence_frames / self.sample_rate
        total_silence_seconds = self._total_silence_frames / self.sample_rate

        end_of_utterance = (
            self._has_speech
            and has_min_speech
            and silence_seconds >= self.end_of_utterance_silence
        )

        conversation_timeout = (
            not self._has_speech
            and total_silence_seconds >= self.conversation_timeout
        )

        return {
            "is_speech": is_speech,
            "rms": float(rms),
            "end_of_utterance": end_of_utterance,
            "conversation_timeout": conversation_timeout,
            "speech_duration": self._speech_frames / self.sample_rate,
        }
