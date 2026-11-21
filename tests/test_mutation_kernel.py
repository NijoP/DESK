"""Roadmap I-1 "one mutation kernel" (report F-6, F-7): every live EasyEDA mutator runs under ops.write_op with an
approval, and the four PCB tools that bypassed it (copper_fill, pcb_rules, stitch_orphans, pcb_place) prove their
effect with an independent readback (desk/reliability/mutation.py + api_registry.py).

Software-tested with fixtures and a fake bridge; not validated on a live design. Each tool runs in a child
interpreter with `desk.bridge.ex` replaced, so the tool's module-level code never touches this test process.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
MIL = 39.37007874

try:
    import shapely  # noqa: F401
    HAVE_SHAPELY = True
except ImportError:
    HAVE_SHAPELY = False

# ---------------------------------------------------------------------------------------------- static scan
# A literal EasyEDA call that creates, deletes, modifies, imports, overwrites, saves or sets state on a primitive.
MUTATOR_RX = re.compile(
    r"eda\.[A-Za-z_]+\.(?:create|delete|modify)[A-Za-z0-9_]*\s*\(|"
    r"\.(?:importChanges|importAutoRouteSesFile|setNetlist|clearRouting|rebuildCopperRegion)\s*\(|"
    r"eda\.[A-Za-z_]+\.overwrite[A-Za-z]*\s*\(|eda\.[A-Za-z_]+\.save\s*\(|\.setState_[A-Za-z0-9_]+\s*\(|"
    r"\bawait\s+[A-Za-z_]+\.delete\s*\(\s*\)")
GUARDS = ("write_op(", "run_live(", "MutationContract(")

# Modules that only BUILD mutating JavaScript (or mention a mutator in prose) and never call the bridge themselves.
# Each maps to the files that execute what it builds; those files must be guarded.
JS_BUILDERS = {
    "desk/draw.py": ["tools/build.py"],
    "desk/routing/outline.py": ["tools/pcb_board.py"],
    "desk/adapters/easyeda_pcb_adapter.py": ["tools/live_disposable_test.py"],
    "desk/copper_fill.py": [],               # docstring mention only; pure geometry
    "desk/reliability/registry.py": [],      # known-failure catalogue text only
}


def _sources():
    for top in ("desk", "tools"):
        for d, _, files in os.walk(os.path.join(ROOT, top)):
            for f in files:
                if f.endswith(".py"):
                    p = os.path.join(d, f)
                    with open(p, encoding="utf-8") as h:
                        yield os.path.relpath(p, ROOT).replace(os.sep, "/"), h.read()


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as h:
        return h.read()


class EveryMutatorUsesWriteOp(unittest.TestCase):
    def test_every_file_with_a_mutator_call_is_guarded(self):
        unguarded = []
        for rel, src in _sources():
            if not MUTATOR_RX.search(src) or rel in JS_BUILDERS:
                continue
            if not any(g in src for g in GUARDS):
                unguarded.append(rel)
        self.assertEqual(unguarded, [], "live EasyEDA mutators outside ops.write_op / run_live")

    def test_js_builders_never_call_the_bridge_and_their_executors_are_guarded(self):
        for rel, executors in JS_BUILDERS.items():
            src = _read(rel)
            self.assertNotIn("from desk.bridge import", src, rel)
            self.assertNotRegex(src, r"\bbridge\.ex\(", rel)
            for e in executors:
                self.assertTrue(any(g in _read(e) for g in GUARDS), f"{e} executes JS from {rel} without write_op")

    def test_the_four_tools_go_through_the_readback_contract(self):
        for t in ("copper_fill", "pcb_rules", "stitch_orphans", "pcb_place"):
            src = _read(f"tools/{t}.py")
            self.assertIn("run_live(", src, t)
            self.assertIn("cli_approve(", src, t)

    def test_the_scan_sees_the_mutators_it_must_see(self):
        # guard against a regex that silently matches nothing
        hits = {rel for rel, src in _sources() if MUTATOR_RX.search(src)}
        for must in ("tools/copper_fill.py", "tools/pcb_rules.py", "tools/stitch_orphans.py", "tools/pcb_place.py",
                     "desk/routing/pipeline.py", "desk/draw.py", "tools/live_disposable_test.py"):
            self.assertIn(must, hits)


# ---------------------------------------------------------------------------------------------- fake bridge
# rules: [[substring, response], ...]; the first rule whose substring is in the script answers it.
_DRIVER = r'''
import json, os, runpy, sys
root, script, rules = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])
sys.path[:0] = [root, root + "/tools"]   # repo root first: tools/desk.py must not shadow desk/
import desk.bridge as B
calls = []
def fake_ex(code, **kw):
    calls.append({"mut": B.looks_mutating(code), "tail": code[-120:]})
    for sub, resp in rules:
        if sub in code:
            return resp
    return None
B.ex = fake_ex
if os.environ.get("FAKE_NO_APPROVAL") == "1":
    import desk.ops as O
    O.cli_approval = lambda *a, **k: None
if os.environ.get("FAKE_PLANE") == "1":           # copper_fill geometry without shapely: one piece per layer
    import desk.copper_fill as CF
    CF.compute_plane_fill = lambda L, *a, **k: {"polygons": ["SQ%d" % L], "area_mm2": 1.0, "removed_islands": 0}
    CF.polygon_to_easyeda_complex = lambda p: [[0, 0, 1, 0, 1, 1]]
sys.argv = [script] + sys.argv[4:]
code = 0
try:
    runpy.run_path(script, run_name="__main__")
except SystemExit as e:
    code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    if not isinstance(e.code, int) and e.code is not None:
        print("EXIT:", e.code)
print("BRIDGE_CALLS=" + json.dumps(len(calls)))
print("MUTATING_CALLS=" + json.dumps(sum(1 for c in calls if c["mut"])))
sys.exit(code)
'''

ACTIVE_DOC = ["return d?d.uuid:null", "PCB1"]


def _run_tool(script, args, rules, **env_extra):
    env = dict(os.environ, DESK_TELEMETRY="0", PYTHONIOENCODING="utf-8")
    env.pop("DESK_MUTATION_POLICY", None)
    env.update(env_extra)
    return subprocess.run([sys.executable, "-c", _DRIVER, ROOT, os.path.join(TOOLS, script), json.dumps(rules), *args],
                          capture_output=True, text=True, timeout=120, env=env, cwd=ROOT)


def _counter(out, name):
    m = re.search(name + r"=(\d+)", out)
    return int(m.group(1)) if m else -1


class _ToolCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.proj = os.path.join(self.tmp, "P")
        os.makedirs(os.path.join(self.proj, "state"))
        os.makedirs(os.path.join(self.proj, "blocks"))
        self._write("project.json", {"name": "FIXTURE", "sheet_uuid": "SHEET1", "pcb_uuid": "PCB1", "window_id": "W1"})

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, rel, obj):
        with open(os.path.join(self.proj, rel), "w", encoding="utf-8") as f:
            json.dump(obj, f)

    def journal(self):
        from desk import ops
        return ops.journal(self.proj)

    def assertRefusedBeforeBridge(self, r):
        out = r.stdout + r.stderr
        self.assertNotEqual(r.returncode, 0, out)
        self.assertIn("no approval was recorded", out)
        self.assertEqual(_counter(r.stdout, "BRIDGE_CALLS"), 0, out)
        self.assertFalse(any(j["phase"] == "begin" for j in self.journal()), "refused run must not journal a begin")
        self.assertFalse(os.path.exists(os.path.join(self.proj, "state", "write.lock")))

    def assertVerified(self, r, op):
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out)
        self.assertIn("VERIFIED by readback", out)
        end = [j for j in self.journal() if j["phase"] == "end" and j["op"] == op]
        self.assertEqual(len(end), 1, out)
        self.assertTrue(end[0]["verified"])
        self.assertEqual(end[0]["execution_state"], "EXECUTED_VERIFIED")
        begin = [j for j in self.journal() if j["phase"] == "begin" and j["op"] == op][0]
        self.assertTrue(begin["approval"], "begin must point at the approval record")
        self.assertEqual(begin["document_uuid"], "PCB1")

    def assertNotComplete(self, r, op):
        out = r.stdout + r.stderr
        self.assertNotEqual(r.returncode, 0, out)
        self.assertIn("NOT VERIFIED", out)
        self.assertGreater(_counter(r.stdout, "MUTATING_CALLS"), 0, out)
        done = [j for j in self.journal() if j["phase"] in ("end", "fail") and j.get("op") == op]
        self.assertEqual(len(done), 1, out)
        self.assertFalse(done[0].get("verified"))
        self.assertNotEqual(done[0].get("execution_state"), "EXECUTED_VERIFIED")


class PcbPlace(_ToolCase):
    def setUp(self):
        super().setUp()
        self._write("state/pcb_dump.json", {"U1": {"id": "c1", "x": 0, "y": 0, "rot": 0, "layer": 1,
                                                   "bbox": [-50, 50, -50, 50], "pads": [{"num": "1", "dx": 0, "dy": 0}]}})
        self._write("placement.json", {"origin_mm": [0, 0], "board_mm": [50, 50],
                                       "parts": [["U1", 10, 10, 0, "T", "fixture"]], "passives": []})

    def rules(self, after):
        return [ACTIVE_DOC, ["pcb_PrimitiveComponent.modify", 1], ["pcb_PrimitiveComponent.get(id)", after]]

    def test_require_policy_refuses_without_approval(self):
        r = _run_tool("pcb_place.py", [self.proj], self.rules({}), DESK_MUTATION_POLICY="require", FAKE_NO_APPROVAL="1")
        self.assertRefusedBeforeBridge(r)

    def test_readback_matching_the_target_is_verified(self):
        r = _run_tool("pcb_place.py", [self.proj], self.rules({"c1": [10 * MIL, 10 * MIL, 0, 1]}))
        self.assertVerified(r, "pcb_place")

    def test_true_return_without_readback_evidence_is_not_complete(self):
        r = _run_tool("pcb_place.py", [self.proj], self.rules({"c1": [0, 0, 0, 1]}))   # modify "worked", nothing moved
        self.assertNotComplete(r, "pcb_place")

    def test_dry_run_records_nothing_and_makes_no_mutation(self):
        r = _run_tool("pcb_place.py", [self.proj, "--dry"], self.rules({}), DESK_MUTATION_POLICY="require",
                      FAKE_NO_APPROVAL="1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(_counter(r.stdout, "MUTATING_CALLS"), 0)
        self.assertEqual(self.journal(), [])


class PcbRules(_ToolCase):
    def setUp(self):
        super().setUp()
        self._write("pcb_rules.json", {"net_classes": {"PWR": ["VBUS"]}, "diff_pairs": {"USB_D": ["USB_DP", "USB_DM"]}})

    def rules(self, readback):
        return [ACTIVE_DOC, ["createNetClass", {"nc": [["PWR", True]], "dp": [["USB_D", True]], "el": []}],
                ["net_classes:L(", readback], ["getAllNetsName", ["VBUS", "USB_DP", "USB_DM"]]]

    def test_require_policy_refuses_without_approval(self):
        r = _run_tool("pcb_rules.py", [self.proj], self.rules({}), DESK_MUTATION_POLICY="require", FAKE_NO_APPROVAL="1")
        self.assertRefusedBeforeBridge(r)

    def test_rules_read_back_are_verified(self):
        r = _run_tool("pcb_rules.py", [self.proj],
                      self.rules({"net_classes": ["PWR"], "diff_pairs": ["USB_D"], "equal_length": []}))
        self.assertVerified(r, "pcb_rules")
        self.assertIn("APPLIED + READ BACK", r.stdout)

    def test_calls_returning_true_without_readback_evidence_are_not_complete(self):
        r = _run_tool("pcb_rules.py", [self.proj], self.rules({"net_classes": [], "diff_pairs": [], "equal_length": []}))
        self.assertNotComplete(r, "pcb_rules")
        self.assertNotIn("APPLIED + READ BACK", r.stdout)


class CopperFill(_ToolCase):
    def setUp(self):
        super().setUp()
        self._write("placement.json", {"board_mm": [20, 20], "origin_mm": [0, 0]})
        self._write("state/copper_fills.json", {"ids": ["OLD1"]})

    def rules(self, readback):
        return [ACTIVE_DOC, ["pcb_PrimitiveFill.create", ["NEW", 0]], ["pcb_PrimitiveFill.getAll", readback],
                ["pcb_PrimitiveFill.delete", True], ["pcb_Document.save", True],
                ["getAllPinsByPrimitiveId", []], ["PrimitiveLine.getAll", []], ["PrimitiveVia.getAll", []]]

    def test_require_policy_refuses_without_approval(self):
        r = _run_tool("copper_fill.py", [self.proj], self.rules([]), DESK_MUTATION_POLICY="require",
                      FAKE_NO_APPROVAL="1", FAKE_PLANE="1")
        self.assertRefusedBeforeBridge(r)

    def test_old_fill_gone_and_new_fill_present_is_verified(self):
        r = _run_tool("copper_fill.py", [self.proj, "--layers", "1"], self.rules(["NEW"]), FAKE_PLANE="1")
        self.assertVerified(r, "copper_fill")

    def test_delete_that_left_the_old_fill_is_not_complete_and_keeps_tracking_it(self):
        r = _run_tool("copper_fill.py", [self.proj, "--layers", "1"], self.rules(["OLD1", "NEW"]), FAKE_PLANE="1")
        self.assertNotComplete(r, "copper_fill")
        with open(os.path.join(self.proj, "state", "copper_fills.json"), encoding="utf-8") as f:
            self.assertIn("OLD1", json.load(f)["ids"])

    def test_remove_with_survivor_is_not_complete(self):
        r = _run_tool("copper_fill.py", [self.proj, "--remove"], self.rules(["OLD1"]), FAKE_PLANE="1")
        self.assertNotComplete(r, "copper_fill")
        self.assertIn('"removed": false', r.stdout)


class StitchOrphans(_ToolCase):
    def setUp(self):
        super().setUp()
        self._write("placement.json", {"board_mm": [20, 20]})

    def test_require_policy_refuses_without_approval(self):
        # The policy check runs before the geometry (shapely) import and before any bridge call.
        r = _run_tool("stitch_orphans.py", [self.proj], [ACTIVE_DOC], DESK_MUTATION_POLICY="require",
                      FAKE_NO_APPROVAL="1")
        self.assertRefusedBeforeBridge(r)

    @unittest.skipUnless(HAVE_SHAPELY, "shapely not installed (stitch_orphans geometry)")
    def test_created_vias_missing_from_readback_are_not_complete(self):
        # One GND SMD pad on the top layer and nothing else: the tool plans a via + track for it.
        pads = [{"ref": "R1", "num": "1", "net": "GND", "x": 10 * MIL, "y": 10 * MIL, "rot": 0,
                 "shape": ["RECT", 40, 40], "layer": 1}]
        rules = [ACTIVE_DOC, ["pcb_PrimitiveVia.create", ["V1"]], ["pcb_PrimitiveLine.create", ["T1"]],
                 ["v.primitiveId).concat", []], ["getAllPinsByPrimitiveId", pads], ["PrimitiveLine.getAll", []],
                 ["PrimitiveVia.getAll", []]]
        r = _run_tool("stitch_orphans.py", [self.proj, "--no-link"], rules)
        if "new vias 0" in r.stdout:
            self.skipTest("fixture produced no orphan via plan")
        self.assertNotComplete(r, "stitch_orphans")


# ---------------------------------------------------------------------------------------------- contract
class RunLiveContract(unittest.TestCase):
    """run_live directly, with fake bridge callables."""

    def setUp(self):
        self.p = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.p, ignore_errors=True)

    def _spec(self, **kw):
        from desk.reliability.mutation import MutationSpec
        base = dict(op="t_op", target="PCB1", document_uuid="PCB1", verifier="ids_present",
                    expected={"ids": ["A"], "planned": 1}, approval="APR", readback_attempts=0)
        base.update(kw)
        return MutationSpec(**base)

    def test_wrong_active_document_refuses_before_execute(self):
        from desk.errors import IdentityUnverified
        from desk.reliability.mutation import run_live
        ran = []
        with self.assertRaises(IdentityUnverified):
            run_live(self.p, {"name": "X", "pcb_uuid": "PCB1"}, lambda js: "OTHER_DOC", self._spec(),
                     lambda: ran.append(1), lambda: [])
        self.assertEqual(ran, [])

    def test_unknown_verifier_never_completes(self):
        from desk.reliability.mutation import run_live
        res = run_live(self.p, {"name": "X", "pcb_uuid": "PCB1"}, lambda js: "PCB1", self._spec(verifier="no_such"),
                       lambda: True, lambda: ["A"])
        self.assertFalse(res.verified)

    def test_require_policy_refuses_before_readback(self):
        from unittest import mock
        from desk.errors import ApprovalRequired
        from desk.reliability.mutation import run_live
        reads = []
        with mock.patch.dict(os.environ, {"DESK_MUTATION_POLICY": "require"}):
            with self.assertRaises(ApprovalRequired):
                run_live(self.p, {"name": "X", "pcb_uuid": "PCB1"}, lambda js: "PCB1", self._spec(approval=None),
                         lambda: True, lambda: reads.append(1) or [])
        self.assertEqual(reads, [])

    def test_verifiers(self):
        from desk.reliability import api_registry as A
        self.assertFalse(A.verify("ids_present", [], [], {"ids": [None], "planned": 1}).passed)   # create returned null
        self.assertTrue(A.verify("ids_present", [], ["A"], {"ids": ["A"], "planned": 1}).passed)
        self.assertTrue(A.verify("ids_present", [], ["A"], ["A"]).passed)                          # old call shape
        self.assertFalse(A.verify("ids_replaced", [], ["O", "N"], {"absent": ["O"], "ids": ["N"], "planned": 1}).passed)
        self.assertTrue(A.verify("ids_replaced", [], ["N"], {"absent": ["O"], "ids": ["N"], "planned": 1}).passed)
        self.assertFalse(A.verify("names_present", {}, {"net_classes": []}, {"net_classes": ["PWR"]}).passed)
        self.assertFalse(A.verify("names_present", {}, {}, {}).passed)                             # nothing checked
        self.assertTrue(A.verify("placements", {}, {"c": [1.0, 2.0, 360, 1]}, {"items": {"c": [1.0, 2.0, 0, 1]}}).passed)
        self.assertFalse(A.verify("placements", {}, {"c": [1.0, 2.0, 90, 1]}, {"items": {"c": [1.0, 2.0, 0, 1]}}).passed)
        self.assertFalse(A.verify("placements", {}, {}, {"items": {}}).passed)


if __name__ == "__main__":
    unittest.main()
