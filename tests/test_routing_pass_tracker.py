"""PassTracker and engine configuration tests, driven by the real Freerouting 2.1.0 log recorded on
projects/WATCH on 2026-11-11 (49 passes, 16.6 min, no SES)."""
import json
import os
import tempfile
import unittest
from unittest import mock

from desk.routing.orchestrator import PassTracker, RoutingEngineOrchestrator

# (pass, seconds, unrouted) exactly as recorded in state/route/freerouting.log
REAL_RUN = [(1, 41.02, 64), (2, 26.52, 51), (3, 24.56, 51), (4, 42.68, 27), (5, 16.41, 18), (6, 9.83, 11), (7, 8.13, 12),
            (8, 17.74, 11), (9, 25.36, 27), (10, 15.62, 28), (11, 14.38, 14), (12, 18.41, 14), (13, 32.59, 26), (14, 10.63, 24),
            (15, 12.06, 24), (16, 28.68, 13), (17, 31.28, 21), (18, 12.24, 14), (19, 6.83, 9), (20, 6.93, 7), (21, 25.45, 18),
            (22, 14.28, 21), (24, 17.96, 14), (25, 21.14, 20), (26, 10.12, 24), (27, 10.98, 18), (28, 20.34, 9), (29, 18.65, 17),
            (30, 9.31, 12), (31, 7.74, 14), (32, 13.14, 8), (33, 26.03, 24), (34, 22.47, 18), (35, 15.05, 14), (36, 11.95, 8),
            (37, 23.25, 15), (38, 10.60, 13), (39, 7.22, 20), (40, 20.24, 8), (41, 21.31, 20), (42, 16.66, 16), (43, 6.31, 22),
            (44, 41.33, 16), (45, 31.74, 20), (46, 17.36, 19), (47, 19.82, 20), (48, 21.16, 17), (49, 22.41, 25)]


def line(p, s, u, score=700.0):
    return (f"2026-11-11 23:0{p % 10}:00.000 INFO   [21609A\\5251DD] Auto-router pass #{p} on board 'abc' was completed "
            f"in {s} seconds with the score of {score} ({u} unrouted), using 1 CPU seconds and 1 MB memory.")


class TestPassTracker(unittest.TestCase):
    def test_parses_real_lines(self):
        t = PassTracker(patience=6)
        rec = t.feed(line(1, 41.02, 64))
        self.assertEqual(rec, {"pass": 1, "seconds": 41.02, "score": 700.0, "unrouted": 64})
        self.assertIsNone(t.feed("2026-11-11 INFO Settings were loaded from freerouting.json"))
        t.feed("INFO   [x] Restoring an earlier board that has the score of 708.76 (51 unrouted).")
        self.assertEqual(t.restores, 1)
        self.assertEqual(t.passes, 1)  # a restore line is not a pass

    def test_identical_count_rule_would_never_fire_but_improvement_rule_does(self):
        t = PassTracker(patience=6)
        stop_at = None
        total_seconds = 0.0
        for p, s, u in REAL_RUN:
            t.feed(line(p, s, u))
            total_seconds += s
            if stop_at is None and t.stagnated():
                stop_at = (p, total_seconds)
        # identical-count rule: never 6 equal consecutive counts in this log
        runs = 1
        longest = 1
        for i in range(1, len(REAL_RUN)):
            runs = runs + 1 if REAL_RUN[i][2] == REAL_RUN[i - 1][2] else 1
            longest = max(longest, runs)
        self.assertLess(longest, 6)
        # improvement rule, patience 6: best 11 at pass 6, six passes without a new best -> stop at pass 12.
        # The full run later reached 7 (pass 20) but burned 16.6 min and wrote no SES; stopping at pass 12
        # keeps 72 % of the engine time. The trade-off is documented in DENSE_BOARD_BENCHMARK_REPORT.md.
        self.assertEqual(t.best_unrouted, 7)   # the tracker keeps following the run after a stop signal
        self.assertEqual(t.best_pass, 20)
        self.assertIsNotNone(stop_at)
        self.assertEqual(stop_at[0], 12)
        full_run_seconds = sum(s for _, s, _ in REAL_RUN)
        self.assertLess(stop_at[1], 0.3 * full_run_seconds)
        # a longer patience (14) rides through the oscillation to the true best and stops at pass 35 (pass 23 is absent in the log)
        t2 = PassTracker(patience=14)
        stop2 = None
        for p, s, u in REAL_RUN:
            t2.feed(line(p, s, u))
            if stop2 is None and t2.stagnated():
                stop2 = p
        self.assertEqual((t2.best_unrouted, t2.best_pass, stop2), (7, 20, 35))

    def test_new_best_resets_patience(self):
        t = PassTracker(patience=3)
        for p, u in [(1, 50), (2, 40), (3, 45), (4, 45), (5, 30), (6, 31), (7, 32)]:
            t.feed(line(p, 1.0, u))
        self.assertFalse(t.stagnated())
        t.feed(line(8, 1.0, 33))
        self.assertTrue(t.stagnated())

    def test_complete_board_never_stagnates(self):
        t = PassTracker(patience=1)
        t.feed(line(1, 1.0, 5))
        t.feed(line(2, 1.0, 0))
        t.feed(line(3, 1.0, 0))
        self.assertFalse(t.stagnated())


class TestEngineConfig(unittest.TestCase):
    def test_build_config_carries_intelligence_outputs(self):
        cfg = RoutingEngineOrchestrator.build_config("00:05:00", max_passes=20, stagnation_pass_limit=4,
                                                     priority_net_classes=["USB_DP", "USB_DM"], plane_nets=["GND", "3V3"],
                                                     via_costs=80, max_threads=1)
        r = cfg["router"]
        self.assertEqual(r["autorouter"]["priority_net_classes"], ["USB_DP", "USB_DM"])
        self.assertEqual(r["plane_nets"], ["GND", "3V3"])
        self.assertEqual(r["autorouter"]["stagnation_pass_limit"], 4)
        self.assertEqual(r["via_costs"], 80)
        self.assertEqual(r["max_passes"], 20)
        self.assertFalse(cfg["gui"]["enabled"])
        self.assertFalse(cfg["profile"]["allow_telemetry"])

    def test_global_config_install_and_restore(self):
        d = tempfile.mkdtemp(prefix="desk_fr_")
        path = os.path.join(d, "freerouting", "freerouting.json")
        os.makedirs(os.path.dirname(path))
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"router": {"job_timeout": "12:00:00", "max_passes": 9999, "scoring": {"via_costs": 50}}}, f)
        with mock.patch.object(RoutingEngineOrchestrator, "global_config_path", return_value=path):
            cfg = RoutingEngineOrchestrator.build_config("00:03:00", max_passes=12, plane_nets=["GND"])
            backup = RoutingEngineOrchestrator.install_global_config(cfg)
            live = json.load(open(path, encoding="utf-8"))
            self.assertEqual(live["router"]["job_timeout"], "00:03:00")
            self.assertEqual(live["router"]["max_passes"], 12)
            self.assertNotIn("plane_nets", live["router"])          # unknown to 2.1: not written (it would break parsing)
            self.assertNotIn("autorouter", live["router"])
            self.assertEqual(live["router"]["scoring"]["via_costs"], 50)  # untouched keys survive the merge
            RoutingEngineOrchestrator.restore_global_config(backup)
            restored = json.load(open(path, encoding="utf-8"))
            self.assertEqual(restored["router"]["max_passes"], 9999)

    def test_highest_compatible_jar_is_selected(self):
        d = tempfile.mkdtemp(prefix="desk_jar_")
        for name in ("freerouting.jar", "freerouting-2.5.0.jar", "freerouting-2.2.4.jar"):
            open(os.path.join(d, name), "wb").close()
        orch = RoutingEngineOrchestrator(tools_dir=d)
        probes = {"freerouting.jar": (True, "v2.1.0"), "freerouting-2.5.0.jar": (False, "UnsupportedClassVersionError"),
                  "freerouting-2.2.4.jar": (True, "v2.2.4")}
        with mock.patch.object(orch, "_probe_jar_compatibility", side_effect=lambda p: probes[os.path.basename(p)]):
            with mock.patch("desk.routing.orchestrator.shutil.which", side_effect=lambda n: "java" if n == "java" else None):
                with mock.patch.dict(os.environ, {"FREEROUTING_JAR": "", "FREEROUTING_BIN": ""}):
                    kind, path, ver = orch.discover_engine()
        self.assertEqual(ver, "v2.2.4")
        self.assertTrue(path.endswith("freerouting-2.2.4.jar"))
        self.assertIn("UnsupportedClassVersionError", orch.last_discovery_note)


if __name__ == "__main__":
    unittest.main()
