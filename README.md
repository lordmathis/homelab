# Homelab

Local AI services (LLM inference, chat, audio) and infrastructure on Mac Mini M4 Pro

## Setup

```sh
cd homebrew
brew bundle install
```

## Services

### LLamactl

[Llamactl](https://github.com/lordmathis/llamactl) provides unified management and routing for llama.cpp, MLX and vLLM models with web dashboard.

```sh
cd llamactl
./setup.sh    # Initial setup
./start.sh    # Start service
./stop.sh     # Stop service
```

### AgentKit

A flexible [chat client](https://github.com/lordmathis/agentkit) with Web UI that integrates multiple AI providers, tools, and agent frameworks through a unified plugin architecture.

```sh
cd agentkit
docker-compose build  # Build service
docker-compose up -d    # Start service
docker-compose down     # Stop service
```

### Audio Service

OpenAI-compatible audio API providing Speech-to-Text transcription and Text-to-Speech generation using [mlx-audio](https://github.com/Blaizzy/mlx-audio). Models are auto-loaded/unloaded based on usage.

```sh
cd audio
./start.sh    # Start service
./stop.sh     # Stop service
```

### Proxy

Nginx reverse proxy configuration generator. Routes traffic to backend services with optional Authelia authentication.

```sh
cd nginx
uv run setup.py  # Generates config and restarts Nginx

brew services stop nginx    # Stop Nginx
```

### Monitoring

Real-time system monitoring dashboard using [Glances](https://github.com/nicolargo/glances). Web-based UI for viewing CPU, memory, disk, and network stats.

```sh
cd glances
./start.sh    # Start service
./stop.sh     # Stop service
```