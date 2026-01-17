#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
HOMELAB_DIR="$(dirname "$SCRIPT_DIR")"

echo "Setting up llamactl..."

# Create necessary directories
echo "Creating directories..."
mkdir -p "$HOME/Library/LaunchAgents"
mkdir -p "$HOME/Library/Application Support/llamactl"
mkdir -p "$HOME/Library/Logs/llamactl"

# Load environment variables from .env
if [[ -f "$SCRIPT_DIR/.env" ]]; then
    echo "Loading environment variables from .env..."
    export $(grep -v '^#' "$SCRIPT_DIR/.env" | xargs)
else
    echo "Warning: .env file not found at $SCRIPT_DIR/.env"
    exit 1
fi

# Generate config.yaml using envsubst
echo "Generating config.yaml from template..."
envsubst < "$SCRIPT_DIR/config.template.yaml" > "$HOME/Library/Application Support/llamactl/config.yaml"
echo "Config generated at: $HOME/Library/Application Support/llamactl/config.yaml"

# Symlink plist file to LaunchAgents
echo "Creating symlink for plist file..."
ln -sf "$SCRIPT_DIR/com.llamactl.plist" "$HOME/Library/LaunchAgents/com.llamactl.plist"
echo "Symlink created: $HOME/Library/LaunchAgents/com.llamactl.plist"

# Unload if already loaded (ignore errors if not loaded)
echo "Unloading existing service (if any)..."
launchctl unload "$HOME/Library/LaunchAgents/com.llamactl.plist" 2>/dev/null || true

# Load the plist file
echo "Loading launchd service..."
launchctl load "$HOME/Library/LaunchAgents/com.llamactl.plist"

echo ""
echo " Setup complete!"
echo ""
echo "Service management commands:"
echo "  Start:  launchctl start com.llamactl"
echo "  Stop:   launchctl stop com.llamactl"
echo "  Status: launchctl list | grep llamactl"
echo ""
echo "Logs location:"
echo "  stdout: $HOME/Library/Logs/llamactl/llamactl.log"
echo "  stderr: $HOME/Library/Logs/llamactl/llamactl.error.log"
