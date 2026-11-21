"""B3: decision graph in the ledger: supersedes, refs-required corrections, `ledger.py history`, rule provenance."""
import glob
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from desk import ledger as LG
from desk.decision_graph import fmt_history, history
from desk.errors import UsageError

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class DecisionHistory(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="desk_hist_")
        self.proj = os.path.join(self.d, "FIX")
        os.makedirs(self.proj)

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def chain(self):
        d1 = LG.add_decision_record(self.proj, "3V3 buck trace width 0.25 mm", "calc qa[2]", req_ids=["REQ-07"],
                                    alternatives=["0.20 mm", "0.30 mm"], reasoning="1.2 A at 10 K rise")
        c = LG.add(self.proj, "correction", "current was 2.0 A, not 1.2 A", source="REQ-07 rev B", refs=d1["id"])
        d2 = LG.add_decision_record(self.proj, "3V3 buck trace width 0.40 mm", "calc qa[2] rerun", req_ids=["REQ-07"],
                                    supersedes=d1["id"], refs=c["id"])
        return d1, c, d2

    def test_history_walks_requirement_decision_correction_new_decision(self):
        d1, c, d2 = self.chain()
        for start in (d1["id"], c["id"], d2["id"]):
            h = history(LG.read(self.proj), start)
            self.assertEqual(h["requirements"], ["REQ-07"])
            self.assertEqual([e["id"] for e in h["chain"]], [d1["id"], d2["id"]])
            self.assertEqual([e["id"] for e in h["corrections"]], [c["id"]])
        out = fmt_history(history(LG.read(self.proj), d2["id"])).splitlines()
        self.assertTrue(out[0].startswith("requirement REQ-07"))
        self.assertIn(f"decision {d1['id']}", out[1])
        self.assertIn(f"correction {c['id']}", out[2])
        self.assertIn(f"new decision {d2['id']}", out[3])
        self.assertIn(d1["id"], LG.superseded(LG.read(self.proj)))
        e = LG.read(self.proj)[0]
        self.assertEqual((e["alternatives"], e["reasoning"]), (["0.20 mm", "0.30 mm"], "1.2 A at 10 K rise"))

    def test_correction_without_refs_is_refused(self):
        with self.assertRaises(UsageError):
            LG.add(self.proj, "correction", "something changed", source="x")
        with self.assertRaises(UsageError):
            LG.add(self.proj, "correction", "something changed", source="x", refs="L-0099")
        with self.assertRaises(UsageError):
            LG.add_decision_record(self.proj, "new", "src", supersedes="L-0042")
        self.assertEqual(LG.read(self.proj), [])

    def test_cli_history_and_decision_options(self):
        tool = os.path.join(ROOT, "tools", "ledger.py")
        run = lambda *args: subprocess.run([sys.executable, tool, self.proj, *args], capture_output=True, text=True, timeout=60)
        r = run("add", "decision", "LDO for the RTC rail", "--source", "BOM_SELECTION F3", "--req-ids", "REQ-02,REQ-05",
                "--alternatives", "buck; shunt", "--reasoning", "quiescent current")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(LG.read(self.proj)[0]["req_ids"], ["REQ-02", "REQ-05"])
        self.assertNotEqual(run("add", "correction", "no refs", "--source", "x").returncode, 0)
        self.assertEqual(run("add", "correction", "Iq too high", "--source", "ds p.3", "--refs", "L-0001").returncode, 0)
        self.assertEqual(run("add", "decision", "buck for the RTC rail", "--source", "rerun", "--supersedes", "L-0001",
                             "--req-ids", "REQ-02").returncode, 0)
        r = run("history", "L-0003")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("requirement REQ-02", r.stdout)
        self.assertIn("correction L-0002", r.stdout)
        self.assertIn("new decision L-0003", r.stdout)

    def test_every_existing_project_ledger_entry_still_loads(self):
        total = 0
        for f in glob.glob(os.path.join(ROOT, "projects", "*", "LEDGER.jsonl")):
            entries = LG.read(os.path.dirname(f))
            LG.superseded(entries)
            for e in entries:
                self.assertIn(e["type"], LG.TYPES)
                fmt_history(history(entries, e["id"]))
            total += len(entries)
        sys.stderr.write(f"\n[measured] existing ledger entries loaded and walked: {total}\n")

    def test_spacing_rule_carries_provenance_without_changing_legacy_output(self):
        from desk.spacing import SpacingPolicy, SpacingRequirement
        kw = dict(net1="HV", net2="GND", voltage_v=230.0, functional_clearance_mm=1.5, creepage_mm=2.5,
                  fabricator_min_mm=0.1, policy=list(SpacingPolicy)[0])
        self.assertNotIn("decision_ref", SpacingRequirement(**kw).to_dict())
        d = SpacingRequirement(decision_ref="L-0019", calc_ref="blocks/01_AC.json#qa[0]", **kw).to_dict()
        self.assertEqual((d["decision_ref"], d["calc_ref"]), ("L-0019", "blocks/01_AC.json#qa[0]"))


if __name__ == "__main__":
    unittest.main()
