#!/bin/bash
set -e

# Get the latest release URL for llamactl
DOWNLOAD_URL=$(curl -s https://api.github.com/repos/lordmathis/llamactl/releases/latest | grep "browser_download_url" | grep "macos-arm64" | grep -v "\.sig" | cut -d '"' -f 4)
INSTALL_DIR="$HOME/bin/llamactl"

# Check dependencies
command -v curl >/dev/null 2>&1 || { echo "curl required"; exit 1; }
command -v tar >/dev/null 2>&1 || { echo "tar required"; exit 1; }

# Check if install directory exists and clean it
if [ -d "$INSTALL_DIR" ]; then
    echo "Removing existing installation..."
    rm -rf "$INSTALL_DIR"/*
else
    echo "Creating installation directory..."
    mkdir -p "$INSTALL_DIR"
fi

# Download and extract
cd /tmp
curl -L -o llamactl.tar.gz "$DOWNLOAD_URL"
tar -xzf llamactl.tar.gz

# Install files (copy all binaries)
cp -r ./* "$INSTALL_DIR/" 2>/dev/null || cp -r * "$INSTALL_DIR/" 2>/dev/null || true
chmod +x "$INSTALL_DIR"/*

# Remove quarantine attributes (only for update scenario)
if [ -d "$INSTALL_DIR" ]; then
    xattr -dr com.apple.quarantine "$INSTALL_DIR"/* 2>/dev/null || true
fi

# Add to PATH if not already present
SHELL_CONFIG="${HOME}/.zshrc"
[[ $SHELL == */bash ]] && SHELL_CONFIG="${HOME}/.bash_profile"

if ! grep -q "$INSTALL_DIR" "$SHELL_CONFIG" 2>/dev/null; then
    echo "export PATH=\"$INSTALL_DIR:\$PATH\"" >> "$SHELL_CONFIG"
    echo "Added to PATH. Run: source $SHELL_CONFIG"
fi

# Cleanup
rm -rf /tmp/llama-* /tmp/llamactl.tar.gz
echo "Done. Installed to $INSTALL_DIR"