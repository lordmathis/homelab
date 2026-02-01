import asyncio
import io
import time
from abc import ABC, abstractmethod

import mlx.core as mx
import soundfile as sf
from mlx_audio.stt.utils import load_model as load_stt_model
from mlx_audio.tts.utils import load_model as load_tts_model

UNLOAD_TIMEOUT_SECONDS = 60 * 60  # 60 minutes
CHECK_INTERVAL_SECONDS = 60  # Check every minute


class ModelManager(ABC):
    def __init__(self):
        self._model = None
        self._last_used: float = 0
        self._checker_task: asyncio.Task | None = None
        self._shutdown = False

    @abstractmethod
    def _load_model(self):
        """Load and return the model. Implemented by subclasses."""

    def _get_model(self):
        """Get the model, loading it if necessary and updating last used time."""
        if self._model is None:
            self._model = self._load_model()
            if self._checker_task is None:
                self._checker_task = asyncio.create_task(self._check_inactivity())

        self._last_used = time.monotonic()
        return self._model

    async def _check_inactivity(self):
        """Periodically check for inactivity and unload model if idle too long."""
        while not self._shutdown:
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)
            if self._model is not None:
                idle_time = time.monotonic() - self._last_used
                if idle_time >= UNLOAD_TIMEOUT_SECONDS:
                    self._model = None
                    self._checker_task = None
                    return

    def shutdown(self):
        self._shutdown = True
        if self._checker_task is not None:
            self._checker_task.cancel()


class STTModelManager(ModelManager):
    def __init__(self):
        super().__init__()
        self.model_name = "mlx-community/whisper-large-v3-turbo-asr-fp16"

    def _load_model(self):
        return load_stt_model(self.model_name)

    def transcribe(self, audio_path: str) -> str:
        """Transcribe audio file to text."""
        return self._get_model().generate(audio=audio_path).text


class TTSModelManager(ModelManager):
    def __init__(self):
        super().__init__()
        self.model_name = "mlx-community/Qwen3-TTS-12Hz-0.6B-Base-bf16"
        self.voice = "Ryan"
        self.language = "English"
        self.sample_rate = 24000

    def _load_model(self):
        return load_tts_model(self.model_name)

    def generate_speech(self, text: str) -> bytes:
        """Generate speech audio from text. Returns WAV bytes."""
        model = self._get_model()

        audio_chunks = []
        for result in model.generate(text, voice=self.voice, language=self.language):
            audio_chunks.append(result.audio)

        if not audio_chunks:
            return b""

        audio = mx.concatenate(audio_chunks, axis=0)

        buffer = io.BytesIO()
        sf.write(buffer, audio, samplerate=self.sample_rate, format="WAV")
        buffer.seek(0)

        return buffer.read()


stt_model_manager = STTModelManager()
tts_model_manager = TTSModelManager()
