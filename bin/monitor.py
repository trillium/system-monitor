#!/usr/bin/env python3
"""System monitor - samples per-core CPU and memory stats, writes to JSON.

Designed to run persistently via launchd (replaces monitor.sh).
Uses macOS Mach APIs via ctypes for per-core CPU without dependencies.
"""

import ctypes
import ctypes.util
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

INTERVAL = int(os.environ.get("MONITOR_INTERVAL", "1"))
DATA_DIR = Path(os.environ.get("MONITOR_DATA_DIR", Path.home() / "code/system-monitor/data"))
STATS_FILE = DATA_DIR / "stats.json"
HISTORY_FILE = DATA_DIR / "history.jsonl"
MAX_HISTORY_SIZE = 50 * 1024 * 1024  # 50MB

DATA_DIR.mkdir(parents=True, exist_ok=True)

# --- Mach API setup for per-core CPU ---
libc = ctypes.CDLL(ctypes.util.find_library("c"))

PROCESSOR_CPU_LOAD_INFO = 2
CPU_STATE_USER = 0
CPU_STATE_SYSTEM = 1
CPU_STATE_IDLE = 2
CPU_STATE_NICE = 3
CPU_STATE_MAX = 4

NUM_CPUS = int(subprocess.check_output(["sysctl", "-n", "hw.ncpu"]).strip())
TOTAL_MEM_MB = int(subprocess.check_output(["sysctl", "-n", "hw.memsize"]).strip()) // 1024 // 1024
_vm_header = subprocess.check_output(["vm_stat"]).decode().split("\n")[0]
PAGE_SIZE = int("".join(c for c in _vm_header.split("size of ")[-1] if c.isdigit()))

_prev_ticks = None


def get_per_core_cpu():
    """Read per-core CPU ticks via Mach host_processor_info, return delta-based percentages."""
    global _prev_ticks

    mach_host = libc.mach_host_self()
    processor_count = ctypes.c_int()
    info_array = ctypes.POINTER(ctypes.c_int)()
    info_count = ctypes.c_int()

    libc.host_processor_info(
        mach_host,
        PROCESSOR_CPU_LOAD_INFO,
        ctypes.byref(processor_count),
        ctypes.byref(info_array),
        ctypes.byref(info_count),
    )

    ncpu = processor_count.value
    current_ticks = []
    for i in range(ncpu):
        offset = i * CPU_STATE_MAX
        current_ticks.append({
            "user": info_array[offset + CPU_STATE_USER],
            "system": info_array[offset + CPU_STATE_SYSTEM],
            "idle": info_array[offset + CPU_STATE_IDLE],
            "nice": info_array[offset + CPU_STATE_NICE],
        })

    per_core = []
    if _prev_ticks and len(_prev_ticks) == ncpu:
        for i in range(ncpu):
            du = current_ticks[i]["user"] - _prev_ticks[i]["user"]
            ds = current_ticks[i]["system"] - _prev_ticks[i]["system"]
            di = current_ticks[i]["idle"] - _prev_ticks[i]["idle"]
            dn = current_ticks[i]["nice"] - _prev_ticks[i]["nice"]
            total = du + ds + di + dn
            if total > 0:
                per_core.append(round(((du + ds) / total) * 100, 1))
            else:
                per_core.append(0.0)
    else:
        # First sample - no delta available, report 0
        per_core = [0.0] * ncpu

    _prev_ticks = current_ticks

    # Aggregate
    if per_core:
        avg = round(sum(per_core) / len(per_core), 1)
    else:
        avg = 0.0

    return per_core, avg


def get_memory():
    """Read memory stats from vm_stat and sysctl."""
    vm = subprocess.check_output(["vm_stat"]).decode()

    def parse_pages(label):
        for line in vm.split("\n"):
            if label in line:
                return int(line.split(":")[-1].strip().rstrip("."))
        return 0

    pages_free = parse_pages("Pages free")
    pages_active = parse_pages("Pages active")
    pages_inactive = parse_pages("Pages inactive")
    pages_wired = parse_pages("Pages wired")
    pages_compressed = parse_pages("Pages occupied by compressor")

    free_mb = (pages_free * PAGE_SIZE) // 1024 // 1024
    active_mb = (pages_active * PAGE_SIZE) // 1024 // 1024
    inactive_mb = (pages_inactive * PAGE_SIZE) // 1024 // 1024
    wired_mb = (pages_wired * PAGE_SIZE) // 1024 // 1024
    compressed_mb = (pages_compressed * PAGE_SIZE) // 1024 // 1024
    used_mb = active_mb + wired_mb + compressed_mb

    try:
        pressure = int(subprocess.check_output(
            ["sysctl", "-n", "kern.memorystatus_vm_pressure_level"]
        ).strip())
    except Exception:
        pressure = 0

    try:
        swap_line = subprocess.check_output(["sysctl", "-n", "vm.swapusage"]).decode()
        swap_total_mb = int(float(swap_line.split("total = ")[1].split("M")[0]))
        swap_used_mb = int(float(swap_line.split("used = ")[1].split("M")[0]))
    except Exception:
        swap_total_mb = 0
        swap_used_mb = 0

    return {
        "total_mb": TOTAL_MEM_MB,
        "used_mb": used_mb,
        "free_mb": free_mb,
        "active_mb": active_mb,
        "inactive_mb": inactive_mb,
        "wired_mb": wired_mb,
        "compressed_mb": compressed_mb,
        "percent": round(used_mb / TOTAL_MEM_MB * 100) if TOTAL_MEM_MB > 0 else 0,
        "pressure": pressure,
        "swap_used_mb": swap_used_mb,
        "swap_total_mb": swap_total_mb,
    }


def sample():
    """Take one sample and write to stats.json + history.jsonl."""
    now = datetime.now(timezone.utc)
    per_core, avg_cpu = get_per_core_cpu()

    # Aggregate CPU (backward compatible)
    # Use avg as approximation for user+sys split
    cpu_user = round(avg_cpu * 0.6, 1)  # rough split
    cpu_sys = round(avg_cpu * 0.4, 1)
    cpu_idle = round(100 - avg_cpu, 1)

    memory = get_memory()

    data = {
        "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "epoch": int(now.timestamp()),
        "cpu": {
            "user": cpu_user,
            "system": cpu_sys,
            "idle": cpu_idle,
            "cores": NUM_CPUS,
            "per_core": per_core,
        },
        "memory": memory,
    }

    # Atomic write to stats.json
    tmp = str(STATS_FILE) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.rename(tmp, str(STATS_FILE))

    # Append to history
    with open(HISTORY_FILE, "a") as f:
        f.write(json.dumps(data) + "\n")


def rotate_history():
    """Rotate history file if it exceeds max size."""
    if HISTORY_FILE.exists() and HISTORY_FILE.stat().st_size > MAX_HISTORY_SIZE:
        lines = HISTORY_FILE.read_text().split("\n")
        keep = len(lines) // 2
        tmp = str(HISTORY_FILE) + ".tmp"
        with open(tmp, "w") as f:
            f.write("\n".join(lines[-keep:]))
        os.rename(tmp, str(HISTORY_FILE))


def main():
    counter = 0
    while True:
        try:
            sample()
        except Exception as e:
            print(f"[monitor] {e}")
        counter += 1
        if counter % 600 == 0:
            rotate_history()
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
