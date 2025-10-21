#!/bin/sh
# Fail fast if the key is missing
if [ -z "$MCPO_API_KEY" ]; then
  echo "Error: MCPO_API_KEY is not set" >&2
  exit 1
fi

# Run the real binary, replacing the shell (so signals go straight to mcpo)
exec mcpo --host 0.0.0.0 --port 8000 \
          --api-key "$MCPO_API_KEY" \
          --config /app/mcpo-config.json \
          --hot-reload