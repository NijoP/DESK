"""Tests for deterministic engineering core: calc, offline ERC, netlist comparator, op journal, release checks."""
import io, json, os, shutil, sys, tempfile, unittest, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from desk import calc, netcheck, ops, release as RL  # noqa: E402


class TestCalc(unittest.TestCase):
    def test_values(self):
        for t, v in (("562k", 562e3), ("4.7uF", 4.7e-6), ("2R2", 2.2), ("4k7", 4700), ("1M", 1e6), ("0R", 0), ("100n", 1e-7), ("33", 33)):
            self.assertAlmostEqual(calc.parse_value(t), v, places=12)
        self.assertIsNone(calc.parse_value("green"))

    def test_divider_pass_fail_and_safety(self):
        b = {"parts": [{"ref": "R1", "value": "562k"}, {"ref": "R2", "value": "100k"}],
             "qa": [{"item": "Vout", "expr": "0.5*(1+R1/R2)", "min": 3.0, "max": 3.6},
                    {"item": "bad", "expr": "0.5*(1+R1/R2)", "min": 3.4, "max": 3.6},
                    {"item": "evil", "expr": "__import__('os')", "min": 0}]}
        r = {i: (v, ok) for i, v, ok, _ in calc.check_qa(b)}
        self.assertAlmostEqual(r["Vout"][0], 3.31); self.assertTrue(r["Vout"][1])
        self.assertFalse(r["bad"][1]); self.assertFalse(r["evil"][1])


class TestNetcheck(unittest.TestCase):
    blocks = [{"id": "B", "parts": [{"ref": "R1", "mpn": "M", "pins": {"1": "A", "2": "GND"}}, {"ref": "C1", "mpn": "M", "pins": {"1": "A", "2": "GND"}}]}]

    def live(self, **over):
        p = [{"ref": "R1", "dev": "M", "pins": [{"num": "1", "net": "A"}, {"num": "2", "net": "GND"}]},
             {"ref": "C1", "dev": "M", "pins": [{"num": "1", "net": "A"}, {"num": "2", "net": "GND"}]}]
        for ref, (num, net) in over.items(): next(q for q in next(x for x in p if x["ref"] == ref)["pins"] if q["num"] == num)["net"] = net
        return p

    def test_identical(self):
        self.assertEqual(netcheck.compare(self.blocks, {"B"}, self.live(), {})[0], [])

    def test_label_collision_detected(self):
        E = netcheck.compare(self.blocks, {"B"}, self.live(C1=("1", "A_X")), {})[0]
        self.assertTrue(any("C1.1" in e for e in E)); self.assertTrue(any("unexpected net A_X" in e for e in E))

    def test_stray_part(self):
        live = self.live() + [{"ref": "R9", "dev": "M", "pins": []}]
        self.assertTrue(any("R9" in e for e in netcheck.compare(self.blocks, {"B"}, live, {})[0]))


class TestOps(unittest.TestCase):
    def setUp(self): self.p = tempfile.mkdtemp()
    def tearDown(self): shutil.rmtree(self.p, ignore_errors=True)

    def test_clean_fail_is_not_pending_dirty_fail_is(self):
        with self.assertRaises(SystemExit):
            with ops.write_op(self.p, "build", "A"): raise SystemExit("STOP before writing")
        self.assertEqual(ops.pending(self.p), [])
        with self.assertRaises(RuntimeError):
            with ops.write_op(self.p, "build", "B") as r:
                r["dirty"] = True; raise RuntimeError("bridge timeout")
        pend = ops.pending(self.p); self.assertEqual([x["target"] for x in pend], ["B"])
        with self.assertRaises(SystemExit):                       # refuses a new write on the dirty target
            with ops.write_op(self.p, "build", "B"): pass
        ops.resolve_pending(self.p, pend[0]["id"], "cleared")
        with ops.write_op(self.p, "build", "B"): pass
        self.assertEqual(ops.pending(self.p), [])

    def test_lock_blocks_second_writer(self):
        with ops.write_op(self.p, "build", "A"):
            with self.assertRaises(SystemExit):
                with ops.write_op(self.p, "build", "C"): pass


class TestRelease(unittest.TestCase):
    def test_bom_and_pnp(self):
        refs = {"R1", "R2", "C1"}
        self.assertEqual(RL.check_bom("Designator,Value\n\"R1,R2\",10k\nC1,1u\n", refs), [])
        self.assertTrue(RL.check_bom("Designator,Value\nR1,10k\n", refs))
        self.assertEqual(RL.check_bom("Designator\tQty\nR1-R2\t2\nC1\t1\n", refs), [])
        self.assertTrue(RL.check_pnp("Designator,Mid X,Mid Y\nR1,1.0mm,2mm\n", refs))

    def test_gerber_and_manifest(self):
        d = tempfile.mkdtemp()
        try:
            z = os.path.join(d, "g.zip")
            with zipfile.ZipFile(z, "w") as f:
                for n in ("Gerber_TopLayer.GTL", "Gerber_BottomLayer.GBL", "Gerber_BoardOutlineLayer.GKO", "Drill_PTH.DRL", "Gerber_TopSolderMaskLayer.GTS"):
                    f.writestr(n, "G04*")
            self.assertEqual(RL.check_gerber(z)[0], [])
            self.assertTrue(RL.check_gerber(z, layers=4)[0])
            RL.write_manifest(d, "A", [z], {"g": {"ok": True}})
            self.assertEqual(RL.verify_manifest(d), [])
            with open(z, "ab") as f: f.write(b"tamper")
            self.assertEqual(RL.verify_manifest(d), ["g.zip"])
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
