#!/bin/bash
set -e

# Get the latest release URL for arm64
DOWNLOAD_URL=$(curl -s https://api.github.com/repos/ggml-org/llama.cpp/releases/latest | grep "browser_download_url" | grep "macos-arm64" | grep -v "\.zip\.sig" | cut -d '"' -f 4 | head -n 1)

if [[ -z "$DOWNLOAD_URL" ]]; then
    echo "Could not find download URL for macos-arm64"
    exit 1
fi

INSTALL_DIR="$HOME/bin/llama-cpp"

# Check dependencies
command -v curl >/dev/null 2>&1 || { echo "curl required"; exit 1; }
command -v unzip >/dev/null 2>&1 || { echo "unzip required"; exit 1; }

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
echo "Downloading llama.cpp from $DOWNLOAD_URL..."
curl -L -o llama-cpp.zip "$DOWNLOAD_URL"

# Create a unique extraction directory to avoid conflicts
EXTRACT_DIR="/tmp/llamacpp-extract-$$"
mkdir -p "$EXTRACT_DIR"
cd "$EXTRACT_DIR"
unzip -q /tmp/llama-cpp.zip

# Find the bin directory (it might be nested)
BIN_DIR=$(find . -name "bin" -type d | head -n 1)
if [[ -z "$BIN_DIR" ]]; then
    echo "Could not find bin directory in extracted files"
    echo "Contents:"
    ls -la
    exit 1
fi

# Install files (copy all binaries from bin directory)
echo "Installing binaries from $BIN_DIR to $INSTALL_DIR"
cp -r "$BIN_DIR"/* "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR"/*

# Remove quarantine attributes (only for macOS)
if [[ "$(uname)" == "Darwin" ]] && [ -d "$INSTALL_DIR" ]; then
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
rm -rf "$EXTRACT_DIR" /tmp/llama-cpp.zip
echo "Done. Installed to $INSTALL_DIR"
