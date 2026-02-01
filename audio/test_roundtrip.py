import argparse
import sys
from pathlib import Path

import requests

BASE_URL = "http://localhost:9020"


def transcribe_audio(audio_path: Path) -> str:
    """Send audio file to transcription endpoint and return the text."""
    url = f"{BASE_URL}/v1/audio/transcriptions"

    with open(audio_path, "rb") as f:
        files = {"file": (audio_path.name, f, "audio/wav")}
        data = {"model": "whisper-1", "response_format": "json"}
        response = requests.post(url, files=files, data=data)

    response.raise_for_status()
    return response.json()["text"]


def text_to_speech(text: str, output_path: Path) -> None:
    """Send text to TTS endpoint and save the audio output."""
    url = f"{BASE_URL}/v1/audio/speech"

    payload = {
        "model": "tts-1",
        "input": text,
        "speed": 1.0,
    }
    response = requests.post(url, json=payload)
    response.raise_for_status()

    with open(output_path, "wb") as f:
        f.write(response.content)


def main():
    parser = argparse.ArgumentParser(description="Test audio transcription and TTS roundtrip")
    parser.add_argument("input_audio", type=Path, help="Path to input audio file")
    args = parser.parse_args()

    if not args.input_audio.exists():
        print(f"Error: Input file '{args.input_audio}' not found")
        sys.exit(1)

    # Step 1: Transcribe the audio
    print(f"Transcribing: {args.input_audio}")
    transcription = transcribe_audio(args.input_audio)
    print(f"Transcription: {transcription}")

    # Step 2: Save transcription to file
    transcription_file = args.input_audio.with_suffix(".txt")
    with open(transcription_file, "w") as f:
        f.write(transcription)
    print(f"Saved transcription to: {transcription_file}")

    # Step 3: Generate speech from transcription
    output_audio = "output.wav"
    print(f"Generating speech...")
    text_to_speech(transcription, output_audio)
    print(f"Saved TTS audio to: {output_audio}")

    print("\nRoundtrip complete!")


if __name__ == "__main__":
    main()
