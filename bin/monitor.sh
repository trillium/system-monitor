#!/bin/bash
# System monitor - samples CPU and memory stats, writes to JSON
# Designed to run persistently via launchd

INTERVAL="${MONITOR_INTERVAL:-1}"
DATA_DIR="${MONITOR_DATA_DIR:-$HOME/code/system-monitor/data}"
STATS_FILE="$DATA_DIR/stats.json"
HISTORY_FILE="$DATA_DIR/history.jsonl"
MAX_HISTORY_SIZE=$((50 * 1024 * 1024))  # 50MB cap, ~3 days at 1s interval

mkdir -p "$DATA_DIR"

# Get number of CPUs once
NUM_CPUS=$(sysctl -n hw.ncpu)
TOTAL_MEM_BYTES=$(sysctl -n hw.memsize)
TOTAL_MEM_MB=$((TOTAL_MEM_BYTES / 1024 / 1024))

get_page_size() {
    vm_stat | head -1 | grep -o '[0-9]*'
}

PAGE_SIZE=$(get_page_size)

sample() {
    local timestamp
    timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    local epoch
    epoch=$(date +%s)

    # CPU usage from top -l2 (first sample is cumulative, second is delta)
    local cpu_line
    cpu_line=$(top -l2 -n0 -s0 2>/dev/null | grep "CPU usage" | tail -1)
    local cpu_user cpu_sys cpu_idle
    cpu_user=$(echo "$cpu_line" | sed 's/.*: \([0-9.]*\)% user.*/\1/')
    cpu_sys=$(echo "$cpu_line" | sed 's/.*user, \([0-9.]*\)% sys.*/\1/')
    cpu_idle=$(echo "$cpu_line" | sed 's/.*sys, \([0-9.]*\)% idle.*/\1/')

    # Memory from vm_stat
    local vm
    vm=$(vm_stat)
    local pages_free pages_active pages_inactive pages_wired pages_compressed pages_speculative
    pages_free=$(echo "$vm" | awk '/Pages free/ {print $NF}' | tr -d '.')
    pages_active=$(echo "$vm" | awk '/Pages active/ {print $NF}' | tr -d '.')
    pages_inactive=$(echo "$vm" | awk '/Pages inactive/ {print $NF}' | tr -d '.')
    pages_wired=$(echo "$vm" | awk '/Pages wired/ {print $NF}' | tr -d '.')
    pages_compressed=$(echo "$vm" | awk '/Pages occupied by compressor/ {print $NF}' | tr -d '.')
    pages_speculative=$(echo "$vm" | awk '/Pages speculative/ {print $NF}' | tr -d '.')

    # Convert to MB
    local free_mb active_mb inactive_mb wired_mb compressed_mb used_mb
    free_mb=$(( (pages_free * PAGE_SIZE) / 1024 / 1024 ))
    active_mb=$(( (pages_active * PAGE_SIZE) / 1024 / 1024 ))
    inactive_mb=$(( (pages_inactive * PAGE_SIZE) / 1024 / 1024 ))
    wired_mb=$(( (pages_wired * PAGE_SIZE) / 1024 / 1024 ))
    compressed_mb=$(( (pages_compressed * PAGE_SIZE) / 1024 / 1024 ))
    used_mb=$(( active_mb + wired_mb + compressed_mb ))

    # Memory pressure (1=normal, 2=warn, 4=critical)
    local pressure
    pressure=$(sysctl -n kern.memorystatus_vm_pressure_level 2>/dev/null || echo "0")

    # Swap
    local swap_line swap_used_mb swap_total_mb
    swap_line=$(sysctl -n vm.swapusage 2>/dev/null)
    swap_total_mb=$(echo "$swap_line" | sed 's/.*total = \([0-9.]*\)M.*/\1/' | cut -d. -f1)
    swap_used_mb=$(echo "$swap_line" | sed 's/.*used = \([0-9.]*\)M.*/\1/' | cut -d. -f1)

    # Build JSON
    local json
    json=$(cat <<EOF
{"timestamp":"${timestamp}","epoch":${epoch},"cpu":{"user":${cpu_user:-0},"system":${cpu_sys:-0},"idle":${cpu_idle:-0},"cores":${NUM_CPUS}},"memory":{"total_mb":${TOTAL_MEM_MB},"used_mb":${used_mb},"free_mb":${free_mb},"active_mb":${active_mb},"inactive_mb":${inactive_mb},"wired_mb":${wired_mb},"compressed_mb":${compressed_mb},"pressure":${pressure},"swap_used_mb":${swap_used_mb:-0},"swap_total_mb":${swap_total_mb:-0}}}
EOF
)

    # Write latest snapshot (atomic via temp file)
    local tmp="$STATS_FILE.tmp"
    echo "$json" > "$tmp"
    mv "$tmp" "$STATS_FILE"

    # Append to history
    echo "$json" >> "$HISTORY_FILE"
}

rotate_history() {
    if [ -f "$HISTORY_FILE" ]; then
        local size
        size=$(stat -f%z "$HISTORY_FILE" 2>/dev/null || echo 0)
        if [ "$size" -gt "$MAX_HISTORY_SIZE" ]; then
            # Keep last ~half of the file
            local lines
            lines=$(wc -l < "$HISTORY_FILE")
            local keep=$((lines / 2))
            tail -n "$keep" "$HISTORY_FILE" > "$HISTORY_FILE.tmp"
            mv "$HISTORY_FILE.tmp" "$HISTORY_FILE"
        fi
    fi
}

rotation_counter=0

while true; do
    sample
    rotation_counter=$((rotation_counter + 1))
    # Check rotation every 600 samples
    if [ $((rotation_counter % 600)) -eq 0 ]; then
        rotate_history
    fi
    sleep "$INTERVAL"
done
