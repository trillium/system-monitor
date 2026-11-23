# system-monitor

Samples per-core CPU and memory once a second (`MONITOR_INTERVAL`) and writes
`stats.json` (atomically) plus an appended `history.jsonl` (capped at 50 MB).
The Talon mode indicator reads `stats.json`.

```json
{"timestamp": "2026-01-02T03:04:05Z", "epoch": 1767323045,
 "cpu": {"average": 12.5, "cores": 16, "per_core": [0.0, 3.1, "..."]},
 "memory": {"total_mb": 31000, "used_mb": 9000, "free_mb": 22000, "percent": 29,
            "pressure": 1, "swap_used_mb": 0, "swap_total_mb": 8000}}
```

`pressure` uses the macOS levels the indicator colours by: 1 normal, 2 warn, 4 critical.

The collector is chosen by platform at startup. Both write the same file.

## macOS

Mach API sampling (`monitor/cpu.py`, `monitor/memory.py`), run by a launchd agent.

```sh
./install.sh            # install / start   (also: uninstall, restart, status)
```

Default data dir: `~/code/system-monitor/data`.

## Linux

`monitor/linux.py` reads `/proc/stat` (per-CPU busy percent from the delta between
samples; the first sample reports 0), `/proc/meminfo` (`percent` = used share of
`MemTotal`, where used = `MemTotal - MemAvailable`; `free_mb` is `MemAvailable`) and
`/proc/pressure/memory` (PSI). The Mac-only `active_mb`, `inactive_mb`, `wired_mb`
and `compressed_mb` keys are omitted.

`pressure` is derived from PSI `avg10` (constants in `monitor/linux.py`):

| Level | Condition |
|-------|-----------|
| 1 normal | `some` avg10 < 5 |
| 2 warn | 5 <= `some` avg10 < 20 |
| 4 critical | `some` avg10 >= 20, or `full` avg10 >= 5 |

If `/proc/pressure/memory` is missing (kernel without PSI) `pressure` is 0.

Run as a systemd user service (logs go to the journal):

```sh
./install.sh            # install, enable and start (also: uninstall, restart, status)
journalctl --user -u system-monitor -f
```

`install.sh` writes `~/.config/systemd/user/system-monitor.service` pointing at the
checkout it is run from, so re-run it if you move the checkout.

Default data dir: `${XDG_DATA_HOME:-~/.local/share}/system-monitor`, unless
`~/code/system-monitor/data` already exists.

## Configuration

| Variable | Default |
|----------|---------|
| `MONITOR_INTERVAL` | `1` (seconds) |
| `MONITOR_DATA_DIR` | see per-OS defaults above |

## Tests

```sh
python3 -m unittest discover -s tests
```
