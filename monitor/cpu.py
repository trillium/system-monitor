"""Per-core CPU sampling via macOS Mach APIs (ctypes)."""

import ctypes
import ctypes.util
import subprocess

libc = ctypes.CDLL(ctypes.util.find_library("c"))

PROCESSOR_CPU_LOAD_INFO = 2
CPU_STATE_USER = 0
CPU_STATE_SYSTEM = 1
CPU_STATE_IDLE = 2
CPU_STATE_NICE = 3
CPU_STATE_MAX = 4

NUM_CPUS = int(subprocess.check_output(["sysctl", "-n", "hw.ncpu"]).strip())

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
