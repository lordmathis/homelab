# Homelab

Local AI services (LLM inference, chat, audio) and infrastructure on Mac Mini M4 Pro.

## Services

| Service | Runtime | Purpose |
|---------|---------|---------|
| llamactl | launchd | LLM model management / routing (llama.cpp, MLX, vLLM) |
| agentkit | Docker (Colima) | Chat UI with tools and skills |
| glances | launchd | System monitoring dashboard |
| audio | launchd | OpenAI-compatible STT + TTS API |

Nginx reverse-proxies all services with optional authentication. Audio is internal only.

## Setup

Install all system dependencies:

```sh
cd homebrew
brew bundle install
```

Secrets go in `.env` files (gitignored). Never commit them. Python projects use `uv` with `pyproject.toml`.

## LLamactl

[Llamactl](https://github.com/lordmathis/llamactl) provides unified management and routing for llama.cpp, MLX and vLLM models with web dashboard. Config is generated from `config.template.yaml` via `setup.sh` (uses `envsubst`).

```sh
cd llamactl
./setup.sh    # Initial setup (generates config from template)
./start.sh    # Start service
./stop.sh     # Stop service
```

## AgentKit

A flexible [chat client](https://github.com/lordmathis/agentkit) with Web UI that integrates multiple AI providers, tools, and agent frameworks through a unified plugin architecture.

```sh
cd agentkit
docker compose up -d --build   # Build and start
docker compose down            # Stop
```

Plugins live in `agentkit/plugins/` and are volume-mounted into the container:

```
plugins/
  tools/<name>/     # Toolset plugin (extends ToolSetHandler, auto-discovered on startup)
  skills/<name>/    # Agent skill (SKILL.md, auto-discovered on startup)
```

AgentKit connects to the audio service via `host.docker.internal:9100`.

## Audio Service

OpenAI-compatible audio API using [mlx-audio](https://github.com/Blaizzy/mlx-audio). Models are lazy-loaded and auto-unloaded after 60 minutes of inactivity.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/audio/transcriptions` | POST | STT via Whisper (`mlx-community/whisper-large-v3-turbo-asr-fp16`) |
| `/v1/audio/speech` | POST | TTS via Chatterbox (`mlx-community/chatterbox-fp16`, 23 languages) |

```sh
cd audio
./start.sh    # Start service
./stop.sh     # Stop service
```

Test scripts: `test_stt.py` (file → transcript) and `test_tts.py` (text/file → WAV, supports `-l` for language).

## Proxy

Nginx reverse proxy with optional Authelia authentication. Routes are declared in `nginx/config.yaml` and rendered via `nginx/setup.py` (Jinja2 template).

```sh
python nginx/setup.py          # Regenerate config, test, and reload Nginx
brew services stop nginx       # Stop Nginx
```

## Monitoring

Real-time system monitoring dashboard using [Glances](https://github.com/nicolargo/glances). Web-based UI for CPU, memory, disk, and network stats.

```sh
cd glances
./start.sh    # Start service
./stop.sh     # Stop service
```
