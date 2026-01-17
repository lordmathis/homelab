#!/bin/bash
set -e

# Get the latest release URL for llamactl
DOWNLOAD_URL=$(curl -s https://api.github.com/repos/lordmathis/llamactl/releases/latest | grep "browser_download_url" | grep "macos-arm64" | grep -v "\.sig" | cut -d '"' -f 4)
INSTALL_PATH="$HOME/bin/llamactl"

# Check dependencies
command -v curl >/dev/null 2>&1 || { echo "curl required"; exit 1; }
command -v tar >/dev/null 2>&1 || { echo "tar required"; exit 1; }

# Check if install path exists and clean it
if [ -f "$INSTALL_PATH" ]; then
    echo "Removing existing installation..."
    rm  "$INSTALL_PATH"
fi

# Download and extract
cd /tmp
echo "Downloading llamactl from $DOWNLOAD_URL..."
curl -L -o llamactl.tar.gz "$DOWNLOAD_URL"
tar -xzf llamactl.tar.gz

# Copy the binary
cp llamactl "$INSTALL_PATH"

# Remove quarantine attributes
if [ -f "$INSTALL_PATH" ]; then
    xattr -dr com.apple.quarantine "$INSTALL_PATH" 2>/dev/null || true
fi

# Add to PATH if not already present
SHELL_CONFIG="${HOME}/.zshrc"
[[ $SHELL == */bash ]] && SHELL_CONFIG="${HOME}/.bash_profile"
PARENT_DIR=$(dirname "$INSTALL_PATH")

if ! grep -q "$PARENT_DIR" "$SHELL_CONFIG"; then
    echo "export PATH=\"\$PATH:$PARENT_DIR\"" >> "$SHELL_CONFIG"
    echo "Added $PARENT_DIR to PATH in $SHELL_CONFIG"
else
    echo "$PARENT_DIR is already in PATH"
fi


# Cleanup
rm -rf /tmp/llama-* /tmp/llamactl.tar.gz
echo "Done. Installed to $INSTALL_PATH"