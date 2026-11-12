"""Regression: `desk.py domains validate <file.json> --project <P>` must read the JSON file (UPS_1000 run, F-003)."""
import json, os, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class DomainsCliArgs(unittest.TestCase):
    def test_validate_reads_file_when_project_flag_given(self):
        req = {"text": "24 V input synchronous buck converter to 5 V 2 A for an industrial controller",
               "voltage_rails": {"VIN": 24.0, "5V": 5.0}, "current_limits_A": {"VIN": 1.0, "5V": 2.0}}
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "req.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump(req, f)
            for argv in ([p, "--project", d, "--json"], ["--project", d, p, "--json"]):
                r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "desk.py"), "domains", "validate", *argv],
                                   capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
                out = json.loads(r.stdout)
                rails = out["compiled"]["design_profile"].get("voltage_rails", {})
                self.assertEqual(rails.get("VIN"), 24.0, msg=f"argv={argv}: declared rails were not read")


if __name__ == "__main__":
    unittest.main()
