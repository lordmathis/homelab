#!/bin/bash
set -e

PLIST_NAME="com.glances.plist"
PLIST_DST="${HOME}/Library/LaunchAgents/${PLIST_NAME}"

# Unload the service if loaded
if [ -e "${PLIST_DST}" ] || [ -L "${PLIST_DST}" ]; then
    launchctl unload "${PLIST_DST}" 2>/dev/null || true
    rm -f "${PLIST_DST}"
    echo "Glances service stopped and plist removed."
else
    echo "Glances service is not installed."
fi
