#!/bin/sh

# Start a persistent headless opencode server (v2 HTTP API) for the mikoshi bridge.
# Runs on 0.0.0.0:4096 so mikoshi (on the host) can reach it via the mapped port.
# Set OPENCODE_SERVER_PASSWORD to enable basic auth.

OPENCODE=/home/coder/.opencode/bin/opencode
[ -x "$OPENCODE" ] || exit 0

mkdir -p /home/coder/workspaces
nohup "$OPENCODE" serve --hostname 0.0.0.0 --port 4096 >/tmp/opencode-serve.log 2>&1 &
