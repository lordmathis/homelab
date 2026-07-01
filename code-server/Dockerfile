FROM codercom/code-server:latest

RUN sudo DEBIAN_FRONTEND=noninteractive apt-get update && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y zsh bat

# uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# nvm
RUN curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.4/install.sh | bash

# Go
RUN curl -LsSf https://go.dev/dl/go1.26.2.linux-amd64.tar.gz | sudo tar -C /usr/local -xzf - 

# opencode
RUN curl -fsSL https://opencode.ai/install | bash

# set zsh
COPY set-zsh.sh /entrypoint.d/

# start opencode serve for the mikoshi bridge
COPY opencode-serve.sh /entrypoint.d/
