FROM ghcr.io/open-webui/mcpo:main

ARG DEBIAN_FRONTEND=noninteractive
ARG GITEA_MCP_VERSION=0.4.0

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        gettext-base \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g @modelcontextprotocol/server-github

RUN curl -L https://gitea.com/gitea/gitea-mcp/releases/download/v${GITEA_MCP_VERSION}/gitea-mcp_Linux_x86_64.tar.gz | tar xz -C /usr/local/bin

COPY mcpo-config.json.tmpl /app/mcpo-config.json.tmpl

COPY entrypoint.sh /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]