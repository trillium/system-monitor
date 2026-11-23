"""Linux sampling via /proc/stat, /proc/meminfo and /proc/pressure/memory (PSI).

Produces the same output shape as the macOS collectors (cpu.py / memory.py):
``get_per_core_cpu()`` -> (per_core, average) and ``get_memory()`` -> dict.

Parsing and maths live in pure functions that take text, so they can be
unit-tested on any OS with fixture /proc content.
"""

# Memory pressure levels. These are the macOS kern.memorystatus_vm_pressure_level
# values the indicator colours by: 1 normal, 2 warn, 4 critical.
PRESSURE_NORMAL = 1
PRESSURE_WARN = 2
PRESSURE_CRITICAL = 4

# PSI thresholds (percent of time stalled, 10 second average).
#   "some" avg10 <  PSI_SOME_WARN                      -> normal   (1)
#   PSI_SOME_WARN <= "some" avg10 < PSI_SOME_CRITICAL  -> warn     (2)
#   "some" avg10 >= PSI_SOME_CRITICAL, or
#   "full" avg10 >= PSI_FULL_CRITICAL                  -> critical (4)
PSI_SOME_WARN = 5.0
PSI_SOME_CRITICAL = 20.0
PSI_FULL_CRITICAL = 5.0

# Reported when /proc/pressure/memory is unavailable (kernel without PSI),
# matching the macOS collector's fallback when sysctl fails.
PRESSURE_UNKNOWN = 0

PROC_STAT = "/proc/stat"
PROC_MEMINFO = "/proc/meminfo"
PROC_PRESSURE_MEMORY = "/proc/pressure/memory"


def _read(path):
    with open(path) as f:
        return f.read()


# --- CPU ---------------------------------------------------------------

def parse_proc_stat(text):
    """Return [(busy, total), ...] jiffies for each logical CPU in /proc/stat.

    Fields after the cpuN label are: user nice system idle iowait irq softirq
    steal guest guest_nice. guest/guest_nice are already counted in
    user/nice, so total covers the first eight. Idle time is idle + iowait.
    """
    cpus = []
    for line in text.splitlines():
        parts = line.split()
        if not parts or not parts[0].startswith("cpu") or parts[0] == "cpu":
            continue
        if not parts[0][3:].isdigit():
            continue
        fields = [int(x) for x in parts[1:9]]
        fields += [0] * (8 - len(fields))  # tolerate older kernels
        total = sum(fields)
        idle = fields[3] + fields[4]
        cpus.append((total - idle, total))
    return cpus


def cpu_percentages(prev, cur):
    """Busy percent per CPU from two parse_proc_stat() snapshots.

    With no usable previous sample (first call, or CPU count changed) every
    core reports 0.0.
    """
    if not prev or len(prev) != len(cur):
        return [0.0] * len(cur)
    result = []
    for (pb, pt), (cb, ct) in zip(prev, cur):
        dtotal = ct - pt
        if dtotal > 0:
            result.append(round(((cb - pb) / dtotal) * 100, 1))
        else:
            result.append(0.0)
    return result


def average(values):
    return round(sum(values) / len(values), 1) if values else 0.0


def _count_cpus():
    try:
        return len(parse_proc_stat(_read(PROC_STAT)))
    except OSError:
        return 0


NUM_CPUS = _count_cpus()

_prev_ticks = None


def get_per_core_cpu():
    """Sample /proc/stat, return (per-core busy percent, average)."""
    global _prev_ticks
    current = parse_proc_stat(_read(PROC_STAT))
    per_core = cpu_percentages(_prev_ticks, current)
    _prev_ticks = current
    return per_core, average(per_core)


# --- Memory ------------------------------------------------------------

def parse_meminfo(text):
    """Return /proc/meminfo as {key: kB} (values without a unit are raw)."""
    info = {}
    for line in text.splitlines():
        key, sep, rest = line.partition(":")
        if not sep:
            continue
        fields = rest.split()
        if fields:
            info[key.strip()] = int(fields[0])
    return info


def parse_psi(text):
    """Parse PSI text into {"some": {"avg10": f, ...}, "full": {...}}."""
    psi = {}
    for line in text.splitlines():
        parts = line.split()
        if not parts:
            continue
        values = {}
        for item in parts[1:]:
            k, _, v = item.partition("=")
            try:
                values[k] = float(v)
            except ValueError:
                pass
        psi[parts[0]] = values
    return psi


def pressure_level(psi):
    """Map parsed PSI to the indicator's pressure level (1, 2 or 4)."""
    if not psi:
        return PRESSURE_UNKNOWN
    some = psi.get("some", {}).get("avg10", 0.0)
    full = psi.get("full", {}).get("avg10", 0.0)
    if some >= PSI_SOME_CRITICAL or full >= PSI_FULL_CRITICAL:
        return PRESSURE_CRITICAL
    if some >= PSI_SOME_WARN:
        return PRESSURE_WARN
    return PRESSURE_NORMAL


def build_memory(meminfo, psi):
    """Build the "memory" dict from parsed meminfo (kB) and parsed PSI.

    used = MemTotal - MemAvailable; free_mb is MemAvailable, so
    used_mb + free_mb == total_mb. The Mac-only active/inactive/wired/
    compressed keys are omitted.
    """
    total_kb = meminfo.get("MemTotal", 0)
    available_kb = meminfo.get("MemAvailable", meminfo.get("MemFree", 0))
    used_kb = max(total_kb - available_kb, 0)
    swap_total_kb = meminfo.get("SwapTotal", 0)
    swap_free_kb = meminfo.get("SwapFree", 0)

    return {
        "total_mb": total_kb // 1024,
        "used_mb": used_kb // 1024,
        "free_mb": available_kb // 1024,
        "percent": round(used_kb / total_kb * 100) if total_kb > 0 else 0,
        "pressure": pressure_level(psi),
        "swap_used_mb": max(swap_total_kb - swap_free_kb, 0) // 1024,
        "swap_total_mb": swap_total_kb // 1024,
    }


def get_memory():
    """Read memory stats from /proc/meminfo and /proc/pressure/memory."""
    meminfo = parse_meminfo(_read(PROC_MEMINFO))
    try:
        psi = parse_psi(_read(PROC_PRESSURE_MEMORY))
    except OSError:
        psi = {}
    return build_memory(meminfo, psi)
