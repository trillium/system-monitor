"""Sampling orchestration — reads CPU + memory, writes JSON output."""

import json
import os
from datetime import datetime, timezone

from .config import STATS_FILE, HISTORY_FILE, MAX_HISTORY_SIZE
from .cpu import get_per_core_cpu, NUM_CPUS
from .memory import get_memory


def sample():
    """Take one sample and write to stats.json + history.jsonl."""
    now = datetime.now(timezone.utc)
    per_core, avg_cpu = get_per_core_cpu()
    memory = get_memory()

    data = {
        "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "epoch": int(now.timestamp()),
        "cpu": {
            "average": avg_cpu,
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
