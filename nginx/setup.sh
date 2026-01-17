#!/bin/bash

set -e

if [ ! -f .env ]; then
    echo "Error: .env file not found"
    exit 1
fi

if [ ! -f nginx.conf.template ]; then
    echo "Error: nginx.conf.template file not found"
    exit 1
fi

set -a
source .env
set +a

# Extract variable names from .env and format for envsubst
ENV_VARS=$(grep -v '^#' .env | grep -v '^$' | cut -d= -f1 | sed 's/^/$/' | tr '\n' ' ')

envsubst "$ENV_VARS" < nginx.conf.template > nginx.conf

nginx -t -c "$(pwd)/nginx.conf"

mkdir -p /opt/homebrew/etc/nginx/servers
cp nginx.conf /opt/homebrew/etc/nginx/servers/lab-proxy.conf

brew services restart nginx

echo "✓ Done"