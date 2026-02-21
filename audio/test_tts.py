import argparse
import sys
from pathlib import Path

import requests

BASE_URL = "http://localhost:9100"


def text_to_speech(text: str, output_path: Path, language: str = "en") -> None:
    """Send text to TTS endpoint and save the audio output."""
    url = f"{BASE_URL}/v1/audio/speech"

    payload = {
        "model": "tts-1",
        "input": text,
        "language": language,
        "speed": 1.0,
    }
    response = requests.post(url, json=payload)
    response.raise_for_status()

    with open(output_path, "wb") as f:
        f.write(response.content)


def main():
    parser = argparse.ArgumentParser(description="Test text-to-speech (TTS)")
    parser.add_argument("text", help="Text to synthesize, or path to a .txt file")
    parser.add_argument("-o", "--output", type=Path, default=Path("output.wav"), help="Output WAV file (default: output.wav)")
    parser.add_argument("-l", "--language", default="en", help="Language code, e.g. en, fr, de, zh (default: en)")
    args = parser.parse_args()

    text_path = Path(args.text)
    if text_path.exists() and text_path.suffix == ".txt":
        text = text_path.read_text().strip()
    else:
        text = args.text

    if not text:
        print("Error: no text provided")
        sys.exit(1)

    print(f"Generating speech (lang={args.language}): {text[:80]}{'...' if len(text) > 80 else ''}")
    text_to_speech(text, args.output, language=args.language)
    print(f"Saved TTS audio to: {args.output}")


if __name__ == "__main__":
    main()
