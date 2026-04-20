#!/bin/bash
set -euo pipefail

tmux kill-session -t logs 2>/dev/null || true
tmux new-session -d -s logs -n llamactl
tmux send-keys 'lnav ~/Library/Logs/llamactl/llamactl.log ~/Library/Logs/llamactl/llamactl.error.log' C-m

tmux new-window -t logs -n audio
tmux send-keys 'lnav ~/Library/Logs/audio/audio.log ~/Library/Logs/audio/audio.error.log' C-m

tmux new-window -t logs -n glances
tmux send-keys 'lnav ~/Library/Logs/glances/glances.log ~/Library/Logs/glances/glances.error.log' C-m

tmux new-window -t logs -n mikoshi
tmux send-keys 'lnav ~/Library/Logs/mikoshi/mikoshi.log' C-m

tmux attach -t logs
