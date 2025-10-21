#!/bin/bash
set -euo pipefail

# --------------------------------------------------------------
#  1️⃣  Verify mandatory environment variables
# --------------------------------------------------------------
: "${MCPO_API_KEY:?MCPO_API_KEY is required}"
: "${GITEA_HOST:-}"
: "${GITEA_ACCESS_TOKEN:-}"
: "${GITHUB_PAT:-}"

# --------------------------------------------------------------
#  2️⃣  Render the JSON configuration from the template
# --------------------------------------------------------------
envsubst < /app/mcpo-config.json.tmpl > /app/mcpo-config.json

# --------------------------------------------------------------
#  3️⃣  Finally start mcpo, replacing the shell process
# --------------------------------------------------------------
exec mcpo --host 0.0.0.0 --port 8000 \
          --api-key "$MCPO_API_KEY" \
          --config /app/mcpo-config.json \
