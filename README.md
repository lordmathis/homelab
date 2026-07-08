# Homelab

Local AI services (LLM inference, chat, audio) and infrastructure on Mac Mini M4 Pro.

## Services

Nginx reverse-proxies all services with optional authentication. Audio and qdrant are internal only. All services are managed through [just](https://github.com/casey/just) recipes in the root `justfile`:

```sh
just <service> start     # start a service
just <service> stop      # stop a service
just <service> restart   # restart a service
```

### Llamactl

[Llamactl](https://github.com/lordmathis/llamactl) provides unified management and routing for llama.cpp, MLX and vLLM models with a web dashboard. Config lives in `llamactl/config.yaml` (env vars like `${LLAMACTL_MGMT_KEY}` are substituted at runtime).

### Mikoshi

A flexible [chat client](https://github.com/lordmathis/mikoshi) with Web UI that integrates multiple AI providers, tools, and agent frameworks through a unified plugin architecture.

Plugins live in `mikoshi/plugins/` and are auto-discovered on startup:

```
plugins/
  tools/<name>.py   # Toolset plugin
  agents/<name>.py  # Agent plugin
  skills/<name>/    # Agent skill
```

### SearXNG

Private [SearXNG](https://github.com/searxng/searxng) meta search engine.

### Audio Service

OpenAI-compatible audio API using [mlx-audio](https://github.com/Blaizzy/mlx-audio). Models are lazy-loaded and auto-unloaded after 60 minutes of inactivity.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/audio/transcriptions` | POST | STT via Whisper (`mlx-community/whisper-large-v3-turbo-asr-fp16`) |
| `/v1/audio/speech` | POST | TTS via Voxtral (`mlx-community/Voxtral-4B-TTS-2603-mlx-bf16`) |

### Code-server

[code-server](https://github.com/coder/code-server) running VS Code in the browser.

### Qdrant

[Qdrant](https://github.com/qdrant/qdrant) vector database.

### Nginx Proxy

Nginx reverse proxy with optional Authelia authentication. Routes are declared in `nginx/config.yaml` and rendered via `nginx/generate.py` (Jinja2 template `lab-proxy.conf.j2`).

### Monitoring

Real-time system monitoring dashboard using [Glances](https://github.com/nicolargo/glances). Web-based UI for CPU, memory, disk, and network stats.

### Logview

Web-based log viewer using ttyd + tmux + lnav. Each service gets its own tmux window with lnav following logs.

### Reachy

Voice-driven agent for the Reachy Mini robot. A standalone Python process (`reachy/voice_assistant/`) listens for a wake word, transcribes speech via the audio service, sends it to mikoshi for processing, and speaks the response back. A mikoshi plugin (`reachy`) and tool server expose robot control to the agent.
