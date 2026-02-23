"""Main loop for the system monitor."""

import time

from .config import INTERVAL, DATA_DIR
from .sampler import sample, rotate_history


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
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
