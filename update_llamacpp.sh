#!/bin/bash
set -e

# Get the latest release URL
DOWNLOAD_URL=$(curl -s https://api.github.com/repos/ggml-org/llama.cpp/releases/latest | grep "browser_download_url" | grep -E "(macos|darwin)" | grep -v "\.zip\.sig" | cut -d '"' -f 4)
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
curl -L -o llama-cpp.zip "$DOWNLOAD_URL"
unzip -q llama-cpp.zip

# Install files (copy all binaries from build/bin)
cp -r /tmp/build/bin/* "$INSTALL_DIR/"
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
rm -rf /tmp/llama-* /tmp/llama-cpp.zip
echo "Done. Installed to $INSTALL_DIR"