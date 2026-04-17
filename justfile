# Homelab services - parent justfile

default:
    @just --list --unsorted

# Audio service (STT + TTS)
audio *ARGS:
    just -f audio/justfile {{ ARGS }}

# Llamactl service
llamactl *ARGS:
    just -f llamactl/justfile {{ ARGS }}

# Nginx proxy config generator
nginx *ARGS:
    just -f nginx/justfile {{ ARGS }}

# Logdy log viewer
logdy *ARGS:
    just -f logdy/justfile {{ ARGS }}

# Homebrew commands and services
brew *ARGS:
    just -f homebrew/justfile {{ ARGS }}

# Glances system monitor
glances *ARGS:
    just -f glances/justfile {{ ARGS }}

# Mikoshi service
mikoshi *ARGS:
    just -f mikoshi/justfile {{ ARGS }}

# Qdrant vector database
qdrant *ARGS:
    just -f qdrant/justfile {{ ARGS }}