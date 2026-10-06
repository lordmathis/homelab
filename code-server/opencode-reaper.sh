#!/bin/sh

# Reap idle opencode TUI sessions to reclaim memory. A TUI waiting for user
# input burns no CPU, so "idle" = its process group's cumulative CPU time
# (the TUI plus any children it spawned, e.g. a running build) has not moved
# for OPENCODE_IDLE_KILL_HOURS (default 12). TERM first, KILL on the next
# pass if it survives. `opencode serve` (mikoshi bridge, pgid 1) never
# matches: it is excluded by both the exact-name match and the pgid 1 guard.

HOURS="${OPENCODE_IDLE_KILL_HOURS:-12}"
INTERVAL="${OPENCODE_REAPER_INTERVAL:-600}"
STATE=/tmp/opencode-reaper.state
LOG=/tmp/opencode-reaper.log

check() {
    NOW=$(date +%s)
    : >"$STATE.new"
    # TUI processes show up as exactly "opencode"; one process group each
    ps -eo pgid,args | awk '$2 == "opencode" && $1 != 1 {print $1}' | sort -u |
    while read -r pgid; do
        [ -n "$pgid" ] || continue
        cpu=$(ps -eo pgid,times,args | awk -v g="$pgid" '$1 == g {s += $2} END {print s + 0}')
        set -- $(awk -v g="$pgid" '$1 == g {print $2, $3, $4}' "$STATE" 2>/dev/null)
        prev_cpu=${1:-}
        prev_seen=${2:-}
        killed=${3:-0}

        if [ -z "$prev_cpu" ]; then
            echo "$pgid $cpu $NOW 0" >>"$STATE.new"
        elif [ "$cpu" != "$prev_cpu" ]; then
            echo "$pgid $cpu $NOW 0" >>"$STATE.new"
        elif [ $((NOW - prev_seen)) -lt $((HOURS * 3600)) ]; then
            echo "$pgid $cpu $prev_seen $killed" >>"$STATE.new"
        elif [ "$killed" = "0" ]; then
            kill -TERM -"$pgid" 2>/dev/null
            echo "$(date -Is) TERM pgid $pgid after ${HOURS}h idle (cpu ${cpu}s)" >>"$LOG"
            echo "$pgid $cpu $prev_seen 1" >>"$STATE.new"
        else
            kill -KILL -"$pgid" 2>/dev/null
            echo "$(date -Is) KILL pgid $pgid (survived TERM)" >>"$LOG"
        fi
    done
    mv "$STATE.new" "$STATE"
}

if [ "$1" = "--loop" ]; then
    while true; do
        check
        sleep "$INTERVAL"
    done
else
    # entrypoint.d scripts must return quickly; daemonize the loop
    nohup "$0" --loop >/dev/null 2>&1 &
fi
