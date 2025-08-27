#!/bin/bash

PLIST_PATH="$HOME/Library/LaunchAgents/com.llamactl.plist"
SERVICE_NAME="com.llamactl"

# Check if service is loaded
if ! launchctl list | grep -q "$SERVICE_NAME"; then
    echo "⚠️  $SERVICE_NAME is not loaded"
    exit 0
fi

# Unload the service
echo "Stopping $SERVICE_NAME..."
launchctl unload "$PLIST_PATH"

# Wait for graceful shutdown (up to 30 seconds)
echo "Waiting for graceful shutdown..."
for i in {1..30}; do
    if ! pgrep -f llamactl > /dev/null; then
        break
    fi
    echo "  Still shutting down... ($i/30)"
    sleep 1
done

# If still running after 30 seconds, try SIGTERM
if pgrep -f llamactl > /dev/null; then
    echo "⚠️  $SERVICE_NAME taking longer than expected, sending SIGTERM..."
    pkill -TERM -f llamactl
    
    # Wait another 10 seconds for SIGTERM to work
    for i in {1..10}; do
        if ! pgrep -f llamactl > /dev/null; then
            break
        fi
        echo "  Waiting for SIGTERM... ($i/10)"
        sleep 1
    done
fi

# Last resort: SIGKILL
if pgrep -f llamactl > /dev/null; then
    echo "❌ Force killing $SERVICE_NAME with SIGKILL..."
    pkill -9 -f llamactl
    sleep 2
fi

# Final check
if ! pgrep -f llamactl > /dev/null; then
    echo "✅ $SERVICE_NAME stopped successfully"
else
    echo "❌ Failed to stop $SERVICE_NAME"
    exit 1
fi