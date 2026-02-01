import io
import tempfile
from contextlib import asynccontextmanager
from typing import Literal, Optional

import mlx.core as mx
import soundfile as sf
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel

from models import stt_model_manager, tts_model_manager


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    stt_model_manager.shutdown()
    tts_model_manager.shutdown()


app = FastAPI(title="Audio API", description="OpenAI-compatible Audio API (STT & TTS)", lifespan=lifespan)


class TranscriptionResponse(BaseModel):
    text: str


@app.post("/v1/audio/transcriptions", response_model=TranscriptionResponse)
async def create_transcription(
    file: UploadFile = File(...),
    model: str = Form(default="whisper-1"),
    language: Optional[str] = Form(default=None),
    prompt: Optional[str] = Form(default=None),
    response_format: str = Form(default="json"),
    temperature: float = Form(default=0.0),
):
    """
    Transcribes audio into the input language.
    Compatible with OpenAI's /v1/audio/transcriptions endpoint.
    """
    # Save uploaded file to a temporary location
    with tempfile.NamedTemporaryFile(delete=False, suffix=file.filename) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    # Generate transcription
    result = stt_model_manager.get_model().generate(audio=tmp_path)

    # Return based on response format
    if response_format == "text":
        return PlainTextResponse(content=result.text)

    return TranscriptionResponse(text=result.text)


class SpeechRequest(BaseModel):
    model: str = "tts-1"
    input: str
    response_format: Literal["wav", "mp3", "flac", "opus"] = "wav"
    speed: float = 1.0


@app.post("/v1/audio/speech")
async def create_speech(request: SpeechRequest):
    """
    Generates audio from the input text.
    Compatible with OpenAI's /v1/audio/speech endpoint.
    """
    model = tts_model_manager.get_model()

    # Generate speech - collect all audio chunks
    audio_chunks = []
    for result in model.generate(
        request.input,
        voice="Ryan",
        language="English"
        ):
        audio_chunks.append(result.audio)

    if not audio_chunks:
        return Response(content=b"", media_type="audio/wav")

    # Concatenate all chunks
    audio = mx.concatenate(audio_chunks, axis=0)

    # Convert to bytes
    buffer = io.BytesIO()
    sf.write(buffer, audio, samplerate=24000, format="WAV")
    buffer.seek(0)

    return Response(content=buffer.read(), media_type="audio/wav")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=9020)