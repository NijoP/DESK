"""desk.doctor (T-18): bounded thread pool, probe cache keyed by executable identity, config check, timing."""
import json
import os
import tempfile
import time
import unittest
from unittest import mock

from desk import doctor


class DoctorCache(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self._orig = doctor.CACHE_PATH
        doctor.CACHE_PATH = os.path.join(self.d, "state", "doctor_cache.json")
        doctor._USE_CACHE = True

    def tearDown(self):
        doctor.CACHE_PATH = self._orig
        doctor._USE_CACHE = True

    def test_cached_value_is_reused_until_signature_changes(self):
        calls = []
        def compute():
            calls.append(1)
            return "java 25"
        self.assertEqual(doctor._cached("java", "sig-A", compute), "java 25")
        self.assertEqual(doctor._cached("java", "sig-A", compute), "java 25")
        self.assertEqual(len(calls), 1)                       # second call served from the cache
        self.assertEqual(doctor._cached("java", "sig-B", compute), "java 25")
        self.assertEqual(len(calls), 2)                       # a different executable identity re-probes
        with open(doctor.CACHE_PATH, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["java"]["sig"], "sig-B")

    def test_ttl_expiry_reprobes(self):
        calls = []
        doctor._cached("node", "s", lambda: calls.append(1) or "v20")
        with open(doctor.CACHE_PATH, encoding="utf-8") as f:
            d = json.load(f)
        d["node"]["ts"] = time.time() - 10 * 86400
        with open(doctor.CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(d, f)
        doctor._cached("node", "s", lambda: calls.append(1) or "v20")
        self.assertEqual(len(calls), 2)

    def test_no_cache_bypasses_read_but_still_stores(self):
        doctor._cached("k", "s", lambda: "first")
        doctor._USE_CACHE = False
        self.assertEqual(doctor._cached("k", "s", lambda: "second"), "second")
        doctor._USE_CACHE = True
        self.assertEqual(doctor._cached("k", "s", lambda: "third"), "second")   # the fresh probe was stored

    def test_signature_changes_with_file_mtime(self):
        p = os.path.join(self.d, "java.exe")
        with open(p, "w") as f:
            f.write("x")
        a = doctor._sig(p)
        os.utime(p, (1, 1))
        self.assertNotEqual(a, doctor._sig(p))
        self.assertEqual(doctor._sig(None), "none")


class DoctorRun(unittest.TestCase):
    def test_runs_all_probes_concurrently_and_survives_a_broken_one(self):
        slow = lambda: (time.sleep(0.3), doctor.Check("slow", doctor.OK, "ok"))[1]
        def boom():
            raise RuntimeError("probe exploded")
        probes = [slow] * 4 + [boom]
        with mock.patch.object(doctor, "_probes", return_value=probes):
            t0 = time.perf_counter()
            checks = doctor.run(project=None)
            dt = time.perf_counter() - t0
        self.assertLess(dt, 0.9, f"four 0.3 s probes must overlap, took {dt:.2f}s")   # sequential would be 1.2 s
        names = [c.name for c in checks]
        self.assertEqual(names.count("slow"), 4)
        broken = [c for c in checks if c.name == "boom"][0]
        self.assertEqual(broken.status, doctor.WARN)
        self.assertIn("probe exploded", broken.detail)
        self.assertEqual(checks[-1].name, "Project")                     # project checks appended last

    def test_config_check_reports_problems(self):
        with mock.patch.dict(os.environ, {"DESK_HTTP_MAX_TOKENS": "many"}):
            c = doctor.check_config()
        self.assertEqual(c.status, doctor.FAIL)
        self.assertIn("DESK_HTTP_MAX_TOKENS", c.detail)

    def test_bridge_scan_probes_ports_in_parallel(self):
        with mock.patch.object(doctor, "_port_open", side_effect=lambda p, timeout=0.1: (time.sleep(0.1), p == 49625)[1]):
            t0 = time.perf_counter()
            c = doctor.check_bridge()
            dt = time.perf_counter() - t0
        self.assertEqual(c.status, doctor.OK)
        self.assertIn("49625", c.detail)
        self.assertLess(dt, 0.6, f"ten 0.1 s probes must overlap, took {dt:.2f}s")

    def test_render_and_main_json(self):
        checks = [doctor.Check("A", doctor.OK, "fine"), doctor.Check("B", doctor.FAIL, "bad", "do X")]
        txt = doctor.render(checks)
        self.assertIn("fix: do X", txt)
        self.assertIn("1 failed, 0 warnings, 1 ok", txt)
        with mock.patch.object(doctor, "run", return_value=checks):
            with mock.patch("builtins.print") as pr:
                rc = doctor.main(["--json"])
        self.assertEqual(rc, 1)
        payload = json.loads(pr.call_args[0][0])
        self.assertEqual(payload["checks"][1]["status"], "FAIL")
        self.assertIn("elapsed_ms", payload)


if __name__ == "__main__":
    unittest.main()
