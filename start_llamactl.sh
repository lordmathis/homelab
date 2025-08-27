#!/bin/bash

PLIST_PATH="$HOME/Library/LaunchAgents/com.llamactl.plist"
SERVICE_NAME="com.llamactl"

# Check if plist exists
if [ ! -f "$PLIST_PATH" ]; then
    echo "Error: $PLIST_PATH not found"
    exit 1
fi

# Load the service
echo "Starting $SERVICE_NAME..."
launchctl load "$PLIST_PATH"

# Check if it's running
sleep 1
if pgrep -f llamactl > /dev/null; then
    echo "✅ $SERVICE_NAME started successfully"
else
    echo "❌ Failed to start $SERVICE_NAME"
    echo "Check logs at: ~/Library/Logs/llamactl/"
    exit 1
fi