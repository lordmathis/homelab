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

# Create .htpasswd file
if [ -z "$USERNAME" ] || [ -z "$PASSWORD" ]; then
    echo "Error: USERNAME and PASSWORD must be set in .env file"
    exit 1
fi

echo "Creating .htpasswd file..."
htpasswd -bc .htpasswd "$USERNAME" "$PASSWORD"
mv .htpasswd /opt/homebrew/etc/nginx/.htpasswd
chmod 644 /opt/homebrew/etc/nginx/.htpasswd
echo "✓ Created .htpasswd file"

# Extract variable names from .env and format for envsubst
ENV_VARS=$(grep -v '^#' .env | grep -v '^$' | cut -d= -f1 | sed 's/^/$/' | tr '\n' ' ')
envsubst "$ENV_VARS" < nginx.conf.template > /opt/homebrew/etc/nginx/servers/lab-proxy.conf

nginx -t

brew services restart nginx

echo "✓ Done"