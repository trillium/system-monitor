"""Sampling orchestration — reads CPU + memory, writes JSON output."""

import json
import os
import sys
import tempfile
from datetime import datetime, timezone

from .config import STATS_FILE, HISTORY_FILE, MAX_HISTORY_SIZE, DATA_DIR

if sys.platform.startswith("linux"):
    from .linux import get_per_core_cpu, get_memory, NUM_CPUS
else:
    from .cpu import get_per_core_cpu, NUM_CPUS
    from .memory import get_memory


def _atomic_write(target, content):
    """Write content to target file atomically via unique temp file + fsync + replace."""
    fd = None
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(dir=str(DATA_DIR), suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            fd = None  # os.fdopen takes ownership
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, str(target))
        tmp_path = None  # replaced successfully
    finally:
        if fd is not None:
            os.close(fd)
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def build_record(now, per_core, avg_cpu, num_cpus, memory):
    """Assemble the stats.json / history.jsonl record."""
    return {
        "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "epoch": int(now.timestamp()),
        "cpu": {
            "average": avg_cpu,
            "cores": num_cpus,
            "per_core": per_core,
        },
        "memory": memory,
    }


def sample():
    """Take one sample and write to stats.json + history.jsonl."""
    now = datetime.now(timezone.utc)
    per_core, avg_cpu = get_per_core_cpu()
    memory = get_memory()
    data = build_record(now, per_core, avg_cpu, NUM_CPUS, memory)

    _atomic_write(STATS_FILE, json.dumps(data))

    # Append to history
    with open(HISTORY_FILE, "a") as f:
        f.write(json.dumps(data) + "\n")


def rotate_history():
    """Rotate history file if it exceeds max size."""
    if HISTORY_FILE.exists() and HISTORY_FILE.stat().st_size > MAX_HISTORY_SIZE:
        lines = HISTORY_FILE.read_text().split("\n")
        keep = len(lines) // 2
        _atomic_write(HISTORY_FILE, "\n".join(lines[-keep:]))
