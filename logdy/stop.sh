#!/bin/bash
set -e

PLIST_NAME="com.logdy.plist"
PLIST_DST="${HOME}/Library/LaunchAgents/${PLIST_NAME}"

if [ -e "${PLIST_DST}" ] || [ -L "${PLIST_DST}" ]; then
    launchctl unload "${PLIST_DST}" 2>/dev/null || true
    rm -f "${PLIST_DST}"
    echo "Logdy stopped and plist removed."
else
    echo "Logdy is not installed."
fi