"""Context Engine + ledger + lint tests. Offline, no EasyEDA. Run: python -m unittest discover -s tests -v"""
import json, os, shutil, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from desk import spec as S, ledger as LG, context as C  # noqa: E402

PINS = {"AP2112K-3.3TRG1": ["VIN", "GND", "EN", "NC", "VOUT"], "CL05A105KA5NQNC": ["1", "2"],
        "0402WGF1003TCE": ["1", "2"], "0402WGF1001TCE": ["1", "2"], "KT-0603G": ["1", "2"]}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.proj = os.path.join(self.tmp, "P")
        shutil.copytree(os.path.join(ROOT, "examples", "demo_node"), self.proj, ignore=shutil.ignore_patterns("state"))
        shutil.copy(os.path.join(ROOT, "templates", "REQUIREMENTS.md"), self.proj)
        self._lib, self._pins = S.LIB_FILE, S.PIN_DIR
        S.LIB_FILE = os.path.join(self.tmp, "lib", "devices.json"); S.PIN_DIR = os.path.join(self.tmp, "lib", "pins")

    def tearDown(self):
        S.LIB_FILE, S.PIN_DIR = self._lib, self._pins
        shutil.rmtree(self.tmp, ignore_errors=True)

    def resolve_all(self, pins=True):
        S.save_library({m: {"libraryUuid": "L", "uuid": "U" + m, "name": m} for m in PINS})
        if pins:
            os.makedirs(S.PIN_DIR, exist_ok=True)
            for m, names in PINS.items():
                with open(os.path.join(S.PIN_DIR, S.safe(m) + ".json"), "w") as h:
                    json.dump([{"num": str(i + 1), "name": n} for i, n in enumerate(names)], h)

    def edit_block(self, fname, fn):
        f = os.path.join(self.proj, "blocks", fname)
        with open(f) as h: b = json.load(h)
        fn(b)
        with open(f, "w") as h: json.dump(b, h, indent=1)


class TestIndex(Base):
    def test_incremental(self):
        a = C.Index(self.proj).stats
        self.assertGreater(a["parsed"], 5)
        b = C.Index(self.proj).stats
        self.assertEqual(b["parsed"], 0)
        self.edit_block("01_PWR_3V3.json", lambda b: b.update(purpose="changed"))
        c = C.Index(self.proj).stats
        self.assertEqual(c["parsed"], 1)

    def test_requirement_rows_indexed(self):
        ix = C.Index(self.proj)
        self.assertIsNotNone(ix.get("req:R-01"))
        self.assertIn("Function", ix.get("req:R-01")["text"])

    def test_doc_sections_have_no_duplicate_heading(self):
        c = C.Index(self.proj).doc("docs/03_BLOCK_WORKFLOW.md", "G4")
        self.assertFalse(c["text"].startswith("##"))

    def test_find_ranks_relevant_section_first(self):
        hits = C.Index(self.proj).find("capacitor dielectric derating", 3)
        self.assertIn("Capacitors", hits[0][1]["title"])


class TestGates(Base):
    def test_gate_progression_and_staleness(self):
        st = lambda: C.Engine(self.proj).state("01_PWR_3V3")
        self.assertEqual(st()["gate"], "G2")
        self.resolve_all(pins=False)
        self.assertEqual(st()["gate"], "G3")
        self.resolve_all(pins=True)
        s = st(); self.assertEqual(s["gate"], "G6", s["errors"])
        LG.add(self.proj, "built", "built", block="01_PWR_3V3", spec_hash=s["hash"])
        self.assertEqual(st()["gate"], "G7")
        LG.add(self.proj, "verified", "ok", block="01_PWR_3V3", spec_hash=s["hash"])
        self.assertEqual(st()["gate"], "ACCEPT")
        self.edit_block("01_PWR_3V3.json", lambda b: b["parts"][1].update(value="2.2uF"))
        s2 = st(); self.assertEqual((s2["gate"], s2["verified"]), ("G7", "stale"))
        self.edit_block("01_PWR_3V3.json", lambda b: b.update(status="accepted"))  # status alone must not un-stale
        self.assertEqual(st()["verified"], "stale")

    def test_status_field_cannot_fake_progress(self):
        self.edit_block("01_PWR_3V3.json", lambda b: b.update(status="accepted"))
        self.assertEqual(C.Engine(self.proj).state("01_PWR_3V3")["gate"], "G2")

    def test_failed_qa_goes_to_g4(self):
        self.resolve_all()
        self.edit_block("01_PWR_3V3.json", lambda b: b["qa"][0].update({"pass": False}))
        self.assertEqual(C.Engine(self.proj).state("01_PWR_3V3")["gate"], "G4")


class TestPacks(Base):
    def test_budgets_respected(self):
        self.resolve_all()
        E = C.Engine(self.proj)
        for text, budget in ((E.brief(300), 300), (E.block("01_PWR_3V3", 400), 400), (E.find("inductor saturation", budget=300), 300),
                             (E.doc("Passive selection", 250), 250)):
            self.assertLessEqual(C.tokens(text), budget * 1.15 + 20, text[-200:])

    def test_block_pack_has_live_lint_and_real_pins(self):
        self.resolve_all()
        self.edit_block("01_PWR_3V3.json", lambda b: b["parts"][0]["pins"].update({"9": "+3V3"}))
        t = C.Engine(self.proj).block("01_PWR_3V3")
        self.assertIn("pin '9' does not exist", t)
        self.assertIn("AP2112K-3.3TRG1: 1=VIN 2=GND 3=EN 4=NC 5=VOUT", t)
        self.assertIn("next gate G5", t)

    def test_block_pack_links_requirements_and_neighbours(self):
        t = C.Engine(self.proj).block("01_PWR_3V3")
        self.assertIn("R-01 |", t)
        self.assertIn("GND -> 02_STATUS_LED:LED1.1", t)

    def test_block_pack_cheaper_than_raw_reading(self):
        self.resolve_all()
        t = C.Engine(self.proj).block("01_PWR_3V3")
        raw = sum(os.path.getsize(os.path.join(ROOT, p)) for p in ("AGENTS.md", "docs/03_BLOCK_WORKFLOW.md", "docs/00b_COMPONENT_SELECTION.md"))
        raw += os.path.getsize(os.path.join(self.proj, "blocks", "01_PWR_3V3.json")) + os.path.getsize(os.path.join(self.proj, "REQUIREMENTS.md"))
        self.assertLess(C.tokens(t), raw / 4 / 3)   # at least 3x fewer tokens than reading the sources

    def test_net_lookup(self):
        t = C.Engine(self.proj).net("GND")
        self.assertIn("01_PWR_3V3: U1.2 C1.2 C2.2", t)
        self.assertIn("02_STATUS_LED: LED1.1", t)
        self.assertIn("Similar", C.Engine(self.proj).net("LDO"))

    def test_delta_incremental(self):
        E = C.Engine(self.proj)
        self.assertIn("first run", E.delta())
        self.assertIn("no changes", C.Engine(self.proj).delta())
        self.edit_block("02_STATUS_LED.json", lambda b: b["parts"][1].update(value="680R"))
        LG.add(self.proj, "decision", "LED dimmer", block="02_STATUS_LED", source="customer mail 2026-01-02")
        d = C.Engine(self.proj).delta()
        self.assertIn("CHANGED block", d); self.assertIn("680R", d); self.assertIn("NEW ledger", d)
        self.assertNotIn("01_PWR_3V3", d)


class TestLedger(Base):
    def test_source_required_and_corrections(self):
        with self.assertRaises(SystemExit):
            LG.add(self.proj, "decision", "no source")
        a = LG.add(self.proj, "fact", "Vout 3.3 V", block="01_PWR_3V3", source="ds p.3")
        LG.add(self.proj, "correction", "Vout 3.28 V min", block="01_PWR_3V3", refs=a["id"], source="ds p.4")
        lines = C.Engine(self.proj).ledger_for("01_PWR_3V3")
        self.assertIn("superseded", lines[0]); self.assertIn("L-0002", lines[1])

    def test_block_hash_ignores_status(self):
        b = S.find_block(self.proj, "01_PWR_3V3"); h = LG.block_hash(b)
        b["status"] = "accepted"; self.assertEqual(h, LG.block_hash(b))
        b["parts"][0]["pins"]["1"] = "X"; self.assertNotEqual(h, LG.block_hash(b))


class TestLint(Base):
    def test_undecided_pin_and_single_net(self):
        self.resolve_all()
        self.assertEqual(S.lint(self.proj, "01_PWR_3V3")[0], [])
        self.edit_block("01_PWR_3V3.json", lambda b: (b["parts"][0]["nc"].clear(), b["parts"][3]["pins"].update({"2": "LDO_ENX"})))
        E = " ".join(S.lint(self.proj, "01_PWR_3V3")[0])
        self.assertIn("neither connected nor in 'nc'", E)
        self.assertIn("LDO_EN touches only U1", E)


if __name__ == "__main__":
    unittest.main()
