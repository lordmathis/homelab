#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLIST_NAME="com.whisper.plist"
PLIST_SRC="${SCRIPT_DIR}/${PLIST_NAME}"
PLIST_DST="${HOME}/Library/LaunchAgents/${PLIST_NAME}"

MODEL_REPO="ggerganov/whisper.cpp"
MODEL_FILE="ggml-large-v3-turbo.bin"

# Download model if not present
if [ ! -f "${SCRIPT_DIR}/${MODEL_FILE}" ]; then
    echo "Model file not found: ${MODEL_FILE}"
    echo "Downloading model from Hugging Face..."
    uv run hf download "$MODEL_REPO" "$MODEL_FILE" --local-dir "${SCRIPT_DIR}"

    if [ ! -f "${SCRIPT_DIR}/${MODEL_FILE}" ]; then
        echo "Failed to download model"
        exit 1
    fi
fi

# Create LaunchAgents directory if it doesn't exist
mkdir -p "${HOME}/Library/LaunchAgents"

# Remove existing symlink or file if present
if [ -e "${PLIST_DST}" ] || [ -L "${PLIST_DST}" ]; then
    launchctl unload "${PLIST_DST}" 2>/dev/null || true
    rm -f "${PLIST_DST}"
fi

# Create symlink
ln -s "${PLIST_SRC}" "${PLIST_DST}"

# Load the service
launchctl load "${PLIST_DST}"

echo "Whisper service started. Access at http://localhost:9100"
