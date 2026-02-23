#!/usr/bin/env python3
"""System monitor entry point (launchd target)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from monitor.main import main

main()
