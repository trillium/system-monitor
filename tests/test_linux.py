"""Linux collector tests. Pure parsers on fixture /proc text; run on any OS.

    python3 -m unittest discover -s tests
"""

import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from monitor import linux  # noqa: E402

STAT_1 = """\
cpu  400 0 200 1400 100 0 0 0 0 0
cpu0 100 0 50 700 50 0 0 0 0 0
cpu1 300 0 150 700 50 0 0 0 0 0
intr 12345
ctxt 6789
btime 1700000000
"""

# +100 ticks on each CPU: cpu0 busy 25 of 100, cpu1 busy 100 of 100.
STAT_2 = """\
cpu  525 0 275 1500 100 0 0 0 0 0
cpu0 125 0 50 775 50 0 0 0 0 0
cpu1 400 0 225 700 50 0 0 0 0 0
intr 12999
"""

MEMINFO = """\
MemTotal:       16384000 kB
MemFree:         2048000 kB
MemAvailable:    4096000 kB
Buffers:          102400 kB
SwapTotal:       8192000 kB
SwapFree:        6144000 kB
HugePages_Total:       0
"""

PSI_OK = """\
some avg10=0.00 avg60=0.10 avg300=0.20 total=9103177
full avg10=0.00 avg60=0.00 avg300=0.00 total=8054484
"""


def psi(some, full=0.0):
    return linux.parse_psi(
        f"some avg10={some:.2f} avg60=0.00 avg300=0.00 total=1\n"
        f"full avg10={full:.2f} avg60=0.00 avg300=0.00 total=1\n"
    )


class ProcStatTests(unittest.TestCase):
    def test_parse_skips_aggregate_and_non_cpu_lines(self):
        cpus = linux.parse_proc_stat(STAT_1)
        self.assertEqual(len(cpus), 2)
        # cpu0: total = 100+50+700+50 = 900, idle = 700+50 -> busy 150
        self.assertEqual(cpus[0], (150, 900))
        self.assertEqual(cpus[1], (450, 1200))

    def test_iowait_and_irq_and_steal(self):
        # user nice system idle iowait irq softirq steal guest guest_nice
        cpus = linux.parse_proc_stat("cpu0 10 5 10 50 20 3 2 5 99 99\n")
        # total = 10+5+10+50+20+3+2+5 = 105; idle = 70; guest ignored
        self.assertEqual(cpus, [(35, 105)])

    def test_delta_math(self):
        prev = linux.parse_proc_stat(STAT_1)
        cur = linux.parse_proc_stat(STAT_2)
        self.assertEqual(linux.cpu_percentages(prev, cur), [25.0, 100.0])

    def test_first_sample_is_zero(self):
        cur = linux.parse_proc_stat(STAT_1)
        self.assertEqual(linux.cpu_percentages(None, cur), [0.0, 0.0])

    def test_cpu_count_change_resets(self):
        prev = linux.parse_proc_stat(STAT_1)[:1]
        cur = linux.parse_proc_stat(STAT_2)
        self.assertEqual(linux.cpu_percentages(prev, cur), [0.0, 0.0])

    def test_no_elapsed_ticks_is_zero(self):
        cur = linux.parse_proc_stat(STAT_1)
        self.assertEqual(linux.cpu_percentages(cur, cur), [0.0, 0.0])

    def test_average(self):
        self.assertEqual(linux.average([25.0, 100.0]), 62.5)
        self.assertEqual(linux.average([]), 0.0)


class MemoryTests(unittest.TestCase):
    def test_parse_meminfo(self):
        info = linux.parse_meminfo(MEMINFO)
        self.assertEqual(info["MemTotal"], 16384000)
        self.assertEqual(info["HugePages_Total"], 0)

    def test_build_memory(self):
        mem = linux.build_memory(linux.parse_meminfo(MEMINFO), linux.parse_psi(PSI_OK))
        self.assertEqual(mem["total_mb"], 16000)
        self.assertEqual(mem["free_mb"], 4000)
        self.assertEqual(mem["used_mb"], 12000)
        self.assertEqual(mem["percent"], 75)
        self.assertEqual(mem["pressure"], 1)
        self.assertEqual(mem["swap_total_mb"], 8000)
        self.assertEqual(mem["swap_used_mb"], 2000)
        for mac_only in ("active_mb", "inactive_mb", "wired_mb", "compressed_mb"):
            self.assertNotIn(mac_only, mem)

    def test_zero_total_does_not_divide(self):
        self.assertEqual(linux.build_memory({}, {})["percent"], 0)


class PressureTests(unittest.TestCase):
    def test_parse_psi(self):
        p = linux.parse_psi(PSI_OK)
        self.assertEqual(p["some"]["avg10"], 0.0)
        self.assertEqual(p["some"]["avg60"], 0.1)
        self.assertEqual(p["full"]["total"], 8054484.0)

    def test_levels(self):
        cases = [
            (0.0, 0.0, 1),
            (4.99, 0.0, 1),
            (5.0, 0.0, 2),
            (19.99, 0.0, 2),
            (20.0, 0.0, 4),
            (80.0, 0.0, 4),
            (1.0, 4.99, 1),
            (1.0, 5.0, 4),   # full avg10 >= 5 is critical even if some is low
            (10.0, 5.0, 4),
        ]
        for some, full, expected in cases:
            with self.subTest(some=some, full=full):
                self.assertEqual(linux.pressure_level(psi(some, full)), expected)

    def test_unavailable_psi(self):
        self.assertEqual(linux.pressure_level({}), linux.PRESSURE_UNKNOWN)

    def test_constants_documented_values(self):
        self.assertEqual(linux.PSI_SOME_WARN, 5.0)
        self.assertEqual(linux.PSI_SOME_CRITICAL, 20.0)
        self.assertEqual(linux.PSI_FULL_CRITICAL, 5.0)


class RecordShapeTests(unittest.TestCase):
    def test_json_shape(self):
        from monitor.sampler import build_record

        cur = linux.parse_proc_stat(STAT_2)
        per_core = linux.cpu_percentages(linux.parse_proc_stat(STAT_1), cur)
        mem = linux.build_memory(linux.parse_meminfo(MEMINFO), linux.parse_psi(PSI_OK))
        now = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
        rec = json.loads(json.dumps(
            build_record(now, per_core, linux.average(per_core), len(cur), mem)))

        self.assertEqual(rec["timestamp"], "2026-01-02T03:04:05Z")
        self.assertEqual(rec["epoch"], int(now.timestamp()))
        self.assertEqual(set(rec), {"timestamp", "epoch", "cpu", "memory"})
        self.assertEqual(rec["cpu"], {"average": 62.5, "cores": 2, "per_core": [25.0, 100.0]})
        self.assertEqual(
            set(rec["memory"]),
            {"total_mb", "used_mb", "free_mb", "percent", "pressure",
             "swap_used_mb", "swap_total_mb"},
        )
        self.assertIsInstance(rec["memory"]["percent"], int)
        self.assertIn(rec["memory"]["pressure"], (1, 2, 4))


if __name__ == "__main__":
    unittest.main()
