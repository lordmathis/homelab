FROM ghcr.io/lordmathis/agentkit:v7

ARG DEBIAN_FRONTEND=noninteractive
ARG GITEA_MCP_VERSION=0.8.0

# Install Node.js, npm, and other dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        gettext-base \
        ca-certificates \
        gnupg \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install gitea-mcp
RUN curl -L https://gitea.com/gitea/gitea-mcp/releases/download/v${GITEA_MCP_VERSION}/gitea-mcp_Linux_x86_64.tar.gz | tar xz -C /usr/local/bin

# Tools dependencies    
RUN uv add caldav icalendar