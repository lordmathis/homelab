#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLIST_NAME="com.audio.plist"
PLIST_SRC="${SCRIPT_DIR}/${PLIST_NAME}"
PLIST_DST="${HOME}/Library/LaunchAgents/${PLIST_NAME}"

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

echo "Audio service started. Access at http://localhost:9100"
