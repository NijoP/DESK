"""F-05: tools/pins.py never targets a default project; it needs an explicit, bound project (no live calls here)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PINS = os.path.join(ROOT, "tools", "pins.py")


def _run(args, cwd):
    env = dict(os.environ, DESK_TELEMETRY="0", PYTHONDONTWRITEBYTECODE="1")
    env.pop("EDA_WINDOW_ID", None)
    return subprocess.run([sys.executable, PINS] + args, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", cwd=cwd, env=env, timeout=60)


class PinsCliTests(unittest.TestCase):
    def test_no_arguments_prints_usage_and_fails(self):
        p = _run([], ROOT)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("no default project", p.stderr + p.stdout)

    def test_mpn_without_project_is_refused(self):
        p = _run(["--mpn", "TPS62840DLCR"], ROOT)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("Usage", p.stderr + p.stdout)

    def test_unbound_project_is_refused_before_any_bridge_call(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "project.json"), "w", encoding="utf-8") as f:
                json.dump({"name": "tmp", "sheet_uuid": "s", "pcb_uuid": "p"}, f)
            p = _run([d, "--mpn", "ANY"], ROOT)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("no window_id", p.stderr + p.stdout)

    def test_source_has_no_hardcoded_project(self):
        with open(PINS, encoding="utf-8") as f:
            src = f.read()
        self.assertNotIn("projects/WATCH", src)
        self.assertIn("ops.write_op", src)


if __name__ == "__main__":
    unittest.main()
