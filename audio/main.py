import tempfile
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from models import model_manager


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    model_manager.shutdown()


app = FastAPI(title="Whisper API", description="OpenAI-compatible Whisper API", lifespan=lifespan)


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
    result = model_manager.get_model().generate(audio=tmp_path)

    # Return based on response format
    if response_format == "text":
        return PlainTextResponse(content=result.text)

    return TranscriptionResponse(text=result.text)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=9020)