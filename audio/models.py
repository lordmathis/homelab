import asyncio
from mlx_audio.stt.utils import load_model

MODEL_NAME = "mlx-community/whisper-large-v3-turbo-asr-fp16"
UNLOAD_TIMEOUT_SECONDS = 60 * 60  # 60 minutes


class ModelManager:
    def __init__(self):
        self._model = None
        self._unload_task: asyncio.Task | None = None

    def get_model(self):
        """Get the model, loading it if necessary and resetting the unload timer."""
        if self._model is None:
            self._model = load_model(MODEL_NAME)

        # Cancel existing unload task and schedule a new one
        if self._unload_task is not None:
            self._unload_task.cancel()
        self._unload_task = asyncio.create_task(self._unload_after_timeout())

        return self._model

    async def _unload_after_timeout(self):
        try:
            await asyncio.sleep(UNLOAD_TIMEOUT_SECONDS)
            self._model = None
            self._unload_task = None
        except asyncio.CancelledError:
            pass  # Expected on shutdown

    def shutdown(self):
        if self._unload_task is not None:
            self._unload_task.cancel()


model_manager = ModelManager()
