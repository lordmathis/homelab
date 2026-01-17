#!/bin/bash

NETDATA_PORT=9004

# Create/overwrite netdata.conf with port configuration
tee /opt/homebrew/etc/netdata/netdata.conf > /dev/null <<EOF
[web]
    default port = ${NETDATA_PORT}
EOF

# Restart netdata
brew services restart netdata