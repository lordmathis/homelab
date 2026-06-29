# Homelab

Local AI services (LLM inference, chat, audio) and infrastructure on Mac Mini M4 Pro.

## Services

| Service | Runtime | Port | Purpose |
|---------|---------|------|---------|
| llamactl | launchd | 9001 | LLM model management / routing (llama.cpp, MLX, vLLM) |
| mikoshi | launchd | 9002 | Chat UI with tools and skills |
| code-server | Docker (Colima) | 9003 | VS Code in the browser |
| searxng | Docker (Colima) | 9004 | Private meta search engine (SearXNG) |
| glances | launchd | 9010 | System monitoring dashboard |
| logview | launchd | 9011 | Log viewer UI (ttyd + tmux + lnav) |
| audio | launchd | 9100 | OpenAI-compatible STT + TTS API |
| qdrant | launchd | 6333 | Vector database |

Nginx reverse-proxies all services with optional authentication. Audio and qdrant are internal only. All services are managed through [just](https://github.com/casey/just) recipes in the root `justfile`:

```sh
just <service> start     # start a service
just <service> stop      # stop a service
just <service> restart   # restart a service
```

## Setup

Install system dependencies via Homebrew:

```sh
just brew update         # or: cd homebrew && brew bundle install
```

Secrets go in `.env` files (gitignored). Never commit them. Python projects use `uv` with `pyproject.toml`. Service binaries (`llamactl`, `qdrant`, `gitea-mcp`) install to `~/bin` via each service's `update` recipe.

## Llamactl

[Llamactl](https://github.com/lordmathis/llamactl) provides unified management and routing for llama.cpp, MLX and vLLM models with a web dashboard. Config lives in `llamactl/config.yaml` (env vars like `${LLAMACTL_MGMT_KEY}` are substituted at runtime).

```sh
just llamactl update     # Download binary to ~/bin
just llamactl start      # Start service
just llamactl stop       # Stop service
```

## Mikoshi

A flexible [chat client](https://github.com/lordmathis/mikoshi) with Web UI that integrates multiple AI providers, tools, and agent frameworks through a unified plugin architecture.

```sh
just mikoshi start       # Start service
just mikoshi stop        # Stop service
just mikoshi restart     # Restart service
```

Plugins live in `mikoshi/plugins/` and are auto-discovered on startup:

```
plugins/
  tools/<name>.py   # Toolset plugin (extends ToolSetHandler)
  agents/<name>.py  # Agent plugin (extends ReActAgentPlugin, etc.)
  skills/<name>/    # Agent skill (SKILL.md)
```

## SearXNG

Private [SearXNG](https://github.com/searxng/searxng) meta search engine, deployed via Docker (Colima) with a Valkey cache.

```sh
just searxng start      # Start service
just searxng stop       # Stop service
just searxng update     # Pull latest images and recreate
just searxng logs       # Follow logs
```

## Audio Service

OpenAI-compatible audio API using [mlx-audio](https://github.com/Blaizzy/mlx-audio). Models are lazy-loaded and auto-unloaded after 60 minutes of inactivity.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/audio/transcriptions` | POST | STT via Whisper (`mlx-community/whisper-large-v3-turbo-asr-fp16`) |
| `/v1/audio/speech` | POST | TTS via Voxtral (`mlx-community/Voxtral-4B-TTS-2603-mlx-bf16`) |

```sh
just audio start         # Start service
just audio stop          # Stop service
```

## Code-server

[code-server](https://github.com/coder/code-server) running VS Code in the browser, deployed via Docker (Colima).

```sh
just code-server start   # Build (if needed) and start
just code-server stop    # Stop
just code-server restart # Restart
```

## Qdrant

[Qdrant](https://github.com/qdrant/qdrant) vector database, run as a launchd service using a native Apple Silicon binary.

```sh
just qdrant update       # Download latest binary to ~/bin
just qdrant start        # Start service
just qdrant stop         # Stop service
```

## Proxy

Nginx reverse proxy with optional Authelia authentication. Routes are declared in `nginx/config.yaml` and rendered via `nginx/generate.py` (Jinja2 template `lab-proxy.conf.j2`).

```sh
just nginx generate      # Regenerate config
just nginx check         # Test config (nginx -t)
just nginx restart       # Reload Nginx via brew services
```

## Monitoring

Real-time system monitoring dashboard using [Glances](https://github.com/nicolargo/glances). Web-based UI for CPU, memory, disk, and network stats.

```sh
just glances start       # Start service
just glances stop        # Stop service
```

## Logview

Web-based log viewer using ttyd + tmux + lnav. Each service gets its own tmux window with lnav following logs.

```sh
just logview start       # Start service
just logview stop        # Stop service
```

## Reachy

Voice-driven agent for the Reachy Mini robot. A standalone Python process (`reachy/voice_assistant/`) listens for a wake word, transcribes speech via the audio service, sends it to mikoshi for processing, and speaks the response back. A mikoshi plugin (`reachy`) and tool server expose robot control to the agent.
