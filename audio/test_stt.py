import argparse
import sys
from pathlib import Path

import requests

BASE_URL = "http://localhost:9100"


def transcribe_audio(audio_path: Path) -> str:
    """Send audio file to transcription endpoint and return the text."""
    url = f"{BASE_URL}/v1/audio/transcriptions"

    with open(audio_path, "rb") as f:
        files = {"file": (audio_path.name, f, "audio/wav")}
        data = {"model": "whisper-1", "response_format": "json"}
        response = requests.post(url, files=files, data=data)

    response.raise_for_status()
    return response.json()["text"]


def main():
    parser = argparse.ArgumentParser(description="Test audio transcription (STT)")
    parser.add_argument("input_audio", type=Path, help="Path to input audio file")
    args = parser.parse_args()

    if not args.input_audio.exists():
        print(f"Error: Input file '{args.input_audio}' not found")
        sys.exit(1)

    print(f"Transcribing: {args.input_audio}")
    transcription = transcribe_audio(args.input_audio)
    print(f"Transcription: {transcription}")

    transcription_file = args.input_audio.with_suffix(".txt")
    with open(transcription_file, "w") as f:
        f.write(transcription)
    print(f"Saved transcription to: {transcription_file}")


if __name__ == "__main__":
    main()
