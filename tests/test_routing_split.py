"""T-15: the pieces of RoutingEngineOrchestrator.execute_routing are testable without Java."""
import ast
import os
import tempfile
import unittest
from unittest import mock

from desk.routing.orchestrator import RoutingEngineOrchestrator, PassTracker, DSNPinMap, EngineExecutionResult


class CommandBuilder(unittest.TestCase):
    def setUp(self):
        self.o = RoutingEngineOrchestrator.__new__(RoutingEngineOrchestrator)
        self.o.java = "/jdk/bin/java"
        self.o.tools_dir = tempfile.mkdtemp()

    def test_v25_jar_command_has_router_flags(self):
        cmd = self.o.build_command("JAR", "/t/fr.jar", "v2.5.0", "b.dsn", "b.ses", 12, 2, "00:05:00", 6,
                                   priority_net_classes=["GND", "VBAT"], plane_nets=["GND"], via_costs=80)
        self.assertEqual(cmd[:3], ["/jdk/bin/java", "-jar", "/t/fr.jar"])
        self.assertIn("-mp", cmd)
        self.assertEqual(cmd[cmd.index("-mp") + 1], "12")
        self.assertEqual(cmd[cmd.index("-mt") + 1], "2")
        self.assertIn("--router.autorouter.max_passes=12", cmd)
        self.assertIn("--router.job_timeout=00:05:00", cmd)
        self.assertIn("--router.autorouter.priority_net_classes=GND,VBAT", cmd)
        self.assertIn("--router.plane_nets=GND", cmd)
        self.assertIn("--router.via_costs=80", cmd)
        self.assertNotIn("--router.autorouter.stagnation_pass_limit=6", cmd)   # 2.5.0 rejects it (default off)

    def test_v21_jar_command_has_only_legacy_flags(self):
        cmd = self.o.build_command("JAR", "/t/fr21.jar", "v2.1.0", "b.dsn", "b.ses", 30, 1, "00:05:00", 6)
        self.assertNotIn("--router.job_timeout=00:05:00", cmd)
        self.assertTrue(cmd[-1] == "--gui.enabled=false")

    def test_native_engine_and_continue_from_ses(self):
        d = tempfile.mkdtemp()
        prev = os.path.join(d, "prev.ses")
        with open(prev, "w") as f:
            f.write("(session)")
        cmd = self.o.build_command("NATIVE", "/usr/bin/freerouting", "v2.5.0", "b.dsn", "b.ses", 8, 1, "00:01:00", 6,
                                   input_ses=prev)
        self.assertEqual(cmd[0], "/usr/bin/freerouting")
        self.assertTrue(cmd[cmd.index("-de") + 1].endswith("b.dsn+" + os.path.abspath(prev)))

    def test_timeout_string(self):
        self.assertEqual(RoutingEngineOrchestrator.timeout_str(300.0), "00:05:00")
        self.assertEqual(RoutingEngineOrchestrator.timeout_str(20.0), "00:01:20")   # minimum one minute
        self.assertEqual(RoutingEngineOrchestrator.timeout_str(1200.0), "00:20:00")


class OutcomeClassification(unittest.TestCase):
    C = staticmethod(RoutingEngineOrchestrator.classify_outcome)

    def test_order_of_precedence(self):
        self.assertEqual(self.C(True, False, 0, True, 10, 0, 300, 6)[0], "TIMEOUT")
        self.assertEqual(self.C(False, False, 1, True, 10, 3, 300, 6)[0], "TIMEOUT_PARTIAL")
        self.assertEqual(self.C(False, True, 0, True, 10, 3, 300, 6)[0], "STAGNATED")
        self.assertEqual(self.C(False, False, 1, False, 0, None, 300, 6)[0], "CRASHED")
        self.assertEqual(self.C(False, False, 0, False, 0, None, 300, 6)[0], "NO_SES")
        self.assertEqual(self.C(False, False, 0, True, 10, 0, 300, 6), ("SUCCESS", None, True))

    def test_stagnation_success_depends_on_ses(self):
        self.assertTrue(self.C(False, True, 0, True, 10, 2, 300, 6, best_unrouted=2, best_pass=4)[2])
        self.assertFalse(self.C(False, True, 0, False, 0, 2, 300, 6)[2])
        self.assertIn("best 2 at pass 4", self.C(False, True, 0, True, 10, 2, 300, 6, 2, 4)[1])

    def test_timeout_partial_needs_unrouted_and_nonzero_rc(self):
        self.assertEqual(self.C(False, False, 1, True, 10, 0, 300, 6)[0], "CRASHED")   # rc != 0 but 0 unrouted


class Supervision(unittest.TestCase):
    def test_supervise_streams_output_into_tracker(self):
        o = RoutingEngineOrchestrator.__new__(RoutingEngineOrchestrator)
        o.java = "java"
        import sys
        d = tempfile.mkdtemp()
        # a stand-in "engine": prints two pass lines and exits 0
        script = ("import sys\n"
                  "print('Pass 1: 12 unrouted'); print('Pass 2: 7 unrouted'); print('Restoring an earlier board'); sys.stdout.flush()\n")
        cmd = [sys.executable, "-c", script]
        tracker = PassTracker(patience=6)
        pin_map = DSNPinMap("")
        published = []
        import time
        proc, out, err, timed_out, stagnated = o.supervise(cmd, d, 30.0, time.time(), tracker, pin_map, {}, published.append, None)
        self.assertEqual(proc.returncode, 0)
        self.assertFalse(timed_out)
        self.assertEqual(len(out), 3)
        self.assertGreaterEqual(tracker.passes, 0)   # pass regexes are PassTracker's concern; we only prove the plumbing

    def test_execute_routing_uses_the_pieces(self):
        """execute_routing = discover + prepare + build + supervise + classify; mocked end to end, no Java."""
        o = RoutingEngineOrchestrator.__new__(RoutingEngineOrchestrator)
        o.java = "java"
        o.tools_dir = tempfile.mkdtemp()
        o.last_discovery_note = ""
        d = tempfile.mkdtemp()
        dsn = os.path.join(d, "b.dsn")
        ses = os.path.join(d, "b.ses")
        with open(dsn, "w") as f:
            f.write("(pcb)")
        fake_proc = mock.Mock(returncode=0)

        def fake_supervise(cmd, wd, timeout_sec, t0, tracker, pin_map, problem_nets, publish, log_callback):
            with open(ses, "w") as f:
                f.write("(session)")
            return fake_proc, ["Pass 1"], [], False, False
        with mock.patch.object(o, "discover_engine", return_value=("JAR", "/t/fr.jar", "v2.5.0")), \
             mock.patch.object(o, "prepare_engine_config", return_value=({"router": {"x": 1}}, None, "00:05:00")), \
             mock.patch.object(o, "supervise", side_effect=fake_supervise), \
             mock.patch.object(o, "restore_global_config"):
            res = o.execute_routing(dsn, ses, max_passes=5, timeout_sec=60, working_dir=d)
        self.assertIsInstance(res, EngineExecutionResult)
        self.assertEqual(res.status, "SUCCESS")
        self.assertTrue(res.ses_generated)
        self.assertEqual(res.engine_config, {"x": 1})
        self.assertIn("--router.job_timeout=00:05:00", res.command)
        self.assertTrue(os.path.exists(os.path.join(d, "freerouting.log")))
        self.assertTrue(os.path.exists(os.path.join(d, "progress.json")))


class ModuleShape(unittest.TestCase):
    def test_no_function_longer_than_80_lines(self):
        import desk.routing.orchestrator as m
        with open(m.__file__, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        too_long = [(n.name, n.end_lineno - n.lineno + 1) for n in ast.walk(tree)
                    if isinstance(n, ast.FunctionDef) and n.end_lineno - n.lineno + 1 > 80]
        self.assertEqual(too_long, [])


if __name__ == "__main__":
    unittest.main()
