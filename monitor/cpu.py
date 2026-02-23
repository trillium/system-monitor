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

# Mach types
mach_port_t = ctypes.c_uint
kern_return_t = ctypes.c_int
vm_address_t = ctypes.c_ulong
vm_size_t = ctypes.c_ulong
mach_msg_type_number_t = ctypes.c_uint

# Configure function signatures
libc.mach_host_self.restype = mach_port_t
libc.mach_host_self.argtypes = []

libc.mach_task_self.restype = mach_port_t
libc.mach_task_self.argtypes = []

libc.host_processor_info.restype = kern_return_t
libc.host_processor_info.argtypes = [
    mach_port_t,                                # host
    ctypes.c_int,                               # flavor
    ctypes.POINTER(ctypes.c_int),               # out_processor_count
    ctypes.POINTER(ctypes.POINTER(ctypes.c_int)),  # out_processor_info
    ctypes.POINTER(mach_msg_type_number_t),     # out_processor_info_count
]

libc.vm_deallocate.restype = kern_return_t
libc.vm_deallocate.argtypes = [
    mach_port_t,    # target_task
    vm_address_t,   # address
    vm_size_t,      # size
]

NUM_CPUS = int(subprocess.check_output(["sysctl", "-n", "hw.ncpu"]).strip())

_prev_ticks = None


def get_per_core_cpu():
    """Read per-core CPU ticks via Mach host_processor_info, return delta-based percentages."""
    global _prev_ticks

    mach_host = libc.mach_host_self()
    processor_count = ctypes.c_int()
    info_array = ctypes.POINTER(ctypes.c_int)()
    info_count = mach_msg_type_number_t()

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

    # Free kernel-allocated memory (leaked ~4KB/call without this)
    array_addr = ctypes.cast(info_array, ctypes.c_void_p).value
    array_size = info_count.value * ctypes.sizeof(ctypes.c_int)
    libc.vm_deallocate(libc.mach_task_self(), array_addr, array_size)

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
