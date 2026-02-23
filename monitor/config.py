"""Configuration constants for the system monitor."""

import os
from pathlib import Path

INTERVAL = int(os.environ.get("MONITOR_INTERVAL", "1"))
DATA_DIR = Path(os.environ.get("MONITOR_DATA_DIR", Path.home() / "code/system-monitor/data"))
STATS_FILE = DATA_DIR / "stats.json"
HISTORY_FILE = DATA_DIR / "history.jsonl"
MAX_HISTORY_SIZE = 50 * 1024 * 1024  # 50MB
