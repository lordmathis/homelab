#!/bin/sh

# Start a persistent headless opencode server (v2 HTTP API) for the mikoshi bridge.
# Runs on 0.0.0.0:4096 so mikoshi (on the host) can reach it via the mapped port.
# Set OPENCODE_SERVER_PASSWORD to enable basic auth.

# opencode 1.17.x has two independent credential stores:
#   - legacy ~/.local/share/opencode/auth.json  (written by `opencode auth login`,
#     read by `opencode run` and the TUI)
#   - the v2 integration store (SQLite, read by the /api/session* endpoints that
#     `opencode serve` exposes)
# The v2 store is NOT populated by auth.json, so any provider authenticated via
# `opencode auth login` comes back as ModelUnavailableError through the HTTP API.
# Below, we mirror each auth.json credential into the v2 store on startup so the
# mikoshi bridge can use them. Secrets are streamed jq -> curl over stdin, so they
# never appear in process argv or logs.

OPENCODE=/home/coder/.opencode/bin/opencode
[ -x "$OPENCODE" ] || exit 0

AUTH="$HOME/.local/share/opencode/auth.json"
BASE_URL="http://localhost:4096"
LOG=/tmp/opencode-serve.log

mkdir -p /home/coder/workspaces
nohup "$OPENCODE" serve --hostname 0.0.0.0 --port 4096 >"$LOG" 2>&1 &

# Wait for the server to accept requests, then register each credential. Runs
# detached so container startup isn't blocked.
(
    i=0
    while [ "$i" -lt 60 ]; do
        curl -fsS -o /dev/null "$BASE_URL/api/integration" 2>/dev/null && break
        i=$((i + 1))
        sleep 1
    done

    if ! command -v jq >/dev/null 2>&1; then
        echo "opencode: jq not found; skipping credential registration" >>"$LOG"
    elif [ ! -f "$AUTH" ]; then
        echo "opencode: $AUTH not found; nothing to register" >>"$LOG"
    else
        # Integration IDs the v2 server actually knows about. Custom providers
        # (declared in config, not integrations) are skipped to avoid 500s.
        integrations=$(curl -fsS "$BASE_URL/api/integration" 2>/dev/null | jq -r '.data[]?.id' 2>/dev/null)
        jq -r 'to_entries[] | .key' "$AUTH" 2>/dev/null | while read -r provider; do
            [ -n "$provider" ] || continue
            if ! printf '%s\n' "$integrations" | grep -qxF "$provider"; then
                echo "opencode: $provider is not a known integration, skipping" >>"$LOG"
                continue
            fi
            # jq emits {"key": "..."} with correct escaping; piped to curl stdin
            # so the secret is never passed as a command-line argument.
            if jq -nc --arg p "$provider" '{"key": .[$p].key}' "$AUTH" 2>/dev/null | \
                curl -fsS -X POST "$BASE_URL/api/integration/$provider/connect/key" \
                    -H "Content-Type: application/json" --data @- -o /dev/null 2>/dev/null; then
                echo "opencode: registered credential for $provider" >>"$LOG"
            else
                echo "opencode: failed to register credential for $provider" >>"$LOG"
            fi
        done
    fi
) &
