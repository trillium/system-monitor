"""Memory sampling via vm_stat and sysctl."""

import subprocess

TOTAL_MEM_MB = int(subprocess.check_output(["sysctl", "-n", "hw.memsize"]).strip()) // 1024 // 1024
_vm_header = subprocess.check_output(["vm_stat"]).decode().split("\n")[0]
PAGE_SIZE = int("".join(c for c in _vm_header.split("size of ")[-1] if c.isdigit()))


def get_memory():
    """Read memory stats from vm_stat and sysctl."""
    vm = subprocess.check_output(["vm_stat"]).decode()

    def parse_pages(label):
        for line in vm.split("\n"):
            if label in line:
                return int(line.split(":")[-1].strip().rstrip("."))
        return 0

    pages_free = parse_pages("Pages free")
    pages_active = parse_pages("Pages active")
    pages_inactive = parse_pages("Pages inactive")
    pages_wired = parse_pages("Pages wired")
    pages_compressed = parse_pages("Pages occupied by compressor")

    free_mb = (pages_free * PAGE_SIZE) // 1024 // 1024
    active_mb = (pages_active * PAGE_SIZE) // 1024 // 1024
    inactive_mb = (pages_inactive * PAGE_SIZE) // 1024 // 1024
    wired_mb = (pages_wired * PAGE_SIZE) // 1024 // 1024
    compressed_mb = (pages_compressed * PAGE_SIZE) // 1024 // 1024
    used_mb = active_mb + wired_mb + compressed_mb

    try:
        pressure = int(subprocess.check_output(
            ["sysctl", "-n", "kern.memorystatus_vm_pressure_level"]
        ).strip())
    except Exception:
        pressure = 0

    try:
        swap_line = subprocess.check_output(["sysctl", "-n", "vm.swapusage"]).decode()
        swap_total_mb = int(float(swap_line.split("total = ")[1].split("M")[0]))
        swap_used_mb = int(float(swap_line.split("used = ")[1].split("M")[0]))
    except Exception:
        swap_total_mb = 0
        swap_used_mb = 0

    return {
        "total_mb": TOTAL_MEM_MB,
        "used_mb": used_mb,
        "free_mb": free_mb,
        "active_mb": active_mb,
        "inactive_mb": inactive_mb,
        "wired_mb": wired_mb,
        "compressed_mb": compressed_mb,
        "percent": round(used_mb / TOTAL_MEM_MB * 100) if TOTAL_MEM_MB > 0 else 0,
        "pressure": pressure,
        "swap_used_mb": swap_used_mb,
        "swap_total_mb": swap_total_mb,
    }
