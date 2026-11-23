"""Configuration constants for the system monitor."""

import os
import sys
from pathlib import Path

LEGACY_DATA_DIR = Path.home() / "code/system-monitor/data"


def default_data_dir():
    """Default data dir: the legacy path, except on Linux when it does not exist."""
    if sys.platform.startswith("linux") and not LEGACY_DATA_DIR.exists():
        xdg = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local/share")
        return Path(xdg) / "system-monitor"
    return LEGACY_DATA_DIR


INTERVAL = int(os.environ.get("MONITOR_INTERVAL", "1"))
DATA_DIR = Path(os.environ.get("MONITOR_DATA_DIR", default_data_dir()))
STATS_FILE = DATA_DIR / "stats.json"
HISTORY_FILE = DATA_DIR / "history.jsonl"
MAX_HISTORY_SIZE = 50 * 1024 * 1024  # 50MB
