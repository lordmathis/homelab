import os
import subprocess
import tempfile
from contextlib import asynccontextmanager
from typing import Literal, Optional

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

    # Convert to WAV format for consistent processing
    wav_path = tmp_path + ".wav"
    try:
        subprocess.run(
            ["ffmpeg", "-i", tmp_path, "-ar", "16000", "-ac", "1", "-y", wav_path],
            check=True,
            capture_output=True,
        )
        text = stt_model_manager.transcribe(wav_path)
    finally:
        os.unlink(tmp_path)
        if os.path.exists(wav_path):
            os.unlink(wav_path)

    if response_format == "text":
        return PlainTextResponse(content=text)

    return TranscriptionResponse(text=text)


class SpeechRequest(BaseModel):
    model: str = "tts-1"
    input: str
    voice: str = "alloy"
    language: str = "en"
    response_format: Literal["wav", "mp3", "flac", "opus"] = "wav"
    speed: float = 1.0


@app.post("/v1/audio/speech")
async def create_speech(request: SpeechRequest):
    """
    Generates audio from the input text.
    Compatible with OpenAI's /v1/audio/speech endpoint.
    """
    audio_bytes = tts_model_manager.generate_speech(request.input, lang_code=request.language)
    return Response(content=audio_bytes, media_type="audio/wav")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=9100)