"""`subsystem` wiring style (docs/02_SCHEMATIC_STYLE.md): policy, net classes, in-block router, geometric checker,
netlist equivalence between styles, the UNVERIFIED-LIVE adapter, the style table, multi-sheet data model and the
migration command. Software-tested with SYNTHETIC fixtures only; nothing here touches EasyEDA or a real project."""
import copy
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from desk import draw, spec as S, schematic_router as R  # noqa: E402
from desk.schematic_io import subsystem_draw_js, create_sheet_js, UNVERIFIED_LIVE  # noqa: E402

FX_DIR = os.path.join(ROOT, "tests", "fixtures", "schematic_wiring")
with open(os.path.join(FX_DIR, "synthetic_project.json"), encoding="utf-8") as _f:
    FX = json.load(_f)
BLOCKS = FX["blocks"]
ORIGIN = {"01_SYN_REG": (100, 3200), "02_SYN_MCU": (1500, 3200)}
# sha256 of desk/draw.py block_js() output for the fixtures, recorded from the code BEFORE the subsystem style landed
LABELS_SHA = {"01_SYN_REG": "3799eb6d07d9aa3b82d4e1dadc0b9c227fa491101c438f5f70feba50ea537353",
              "02_SYN_MCU": "6b01a15fcdf0d1c2f8e897a1ccd038065ef26c198cf2b2f8a97afdb874ff188c"}


def synthetic_place(block, x0, yt, pitch=10):
    """A deterministic stand-in for PLACE_JS's read-back: ICs in a row at the top (left pins rot 180, right pins
    rot 0, `pitch` apart), 2-pin passives in a grid below, spaced like desk/draw.py BLOCK_JS."""
    st = draw.STYLE
    pins, x, bottom, right = {}, x0 + st["pad"], yt, x0
    for p in block["parts"]:
        if p.get("kind") == "passive":
            continue
        n = len(p.get("pins", {})) + len(p.get("nc", []))
        nums = [str(i) for i in range(1, n + 1)]
        left, rgt = nums[: (n + 1) // 2], nums[(n + 1) // 2:]
        lx = x + st["stub"][1] + 50
        top = yt - st["title_h"] - 40
        rx = lx + 60
        pins[p["ref"]] = ([{"num": k, "x": lx, "y": top - i * pitch, "rot": 180} for i, k in enumerate(left)] +
                          [{"num": k, "x": rx, "y": top - i * pitch, "rot": 0} for i, k in enumerate(rgt)])
        bottom = min(bottom, top - max(len(left), len(rgt)) * pitch - 40)
        x = rx + st["stub"][1] + 80 + st["gap_x"]
        right = max(right, x)
    cols = 3
    y, i = bottom - 90, 0
    for p in block["parts"]:
        if p.get("kind") != "passive":
            continue
        row_h = -(-st["row_h"] // 10) * 10                 # PLACE_JS snaps the passive row pitch to the grid
        cx, cy = x0 + st["pad"] + 170 + (i % cols) * st["pitch"], y - (i // cols) * row_h
        pins[p["ref"]] = [{"num": "1", "x": cx - 20, "y": cy, "rot": 180}, {"num": "2", "x": cx + 20, "y": cy, "rot": 0}]
        i += 1
    rows = (i + cols - 1) // cols
    low = y - (rows - 1) * (-(-st["row_h"] // 10) * 10) - 80
    W = max(right - x0, cols * st["pitch"] + st["pad"] + 40)
    return {"W": W, "H": yt - low, "REF": {r: r for r in pins}, "PINS": pins}


def plans(block):
    x0, yt = ORIGIN[block["id"]]
    placed = synthetic_place(block, x0, yt)
    return placed, draw.plan_subsystem(block, BLOCKS, placed, x0, yt, {}), R.plan_labels(block, placed["PINS"])


class LabelsStyleUnchanged(unittest.TestCase):
    def test_block_js_is_byte_identical_to_before(self):
        for b in BLOCKS:
            js = draw.block_js(b, FX["library"], *ORIGIN[b["id"]], FX["pin_counts"])
            self.assertEqual(hashlib.sha256(js.encode("utf-8")).hexdigest(), LABELS_SHA[b["id"]], b["id"])
            with open(os.path.join(FX_DIR, f"labels_{b['id']}.golden.js"), encoding="utf-8") as f:
                self.assertEqual(js, f.read().replace("\r\n", "\n"))

    def test_place_js_is_block_js_without_labels_or_frame(self):
        js = draw.place_js(BLOCKS[0], FX["library"], 100, 3200, FX["pin_counts"])
        self.assertNotIn("await labelPins(", js)
        self.assertNotIn("sch_PrimitiveRectangle.create", js)
        self.assertNotIn("sch_PrimitiveText.create", js)
        self.assertIn("return {W,H,REF,PINS};", js)
        self.assertIn("await nc(id,p.nc)", js)              # NC flags are still set in phase 1
        self.assertIn("ROWH=Math.ceil(S.row_h/10)*10", js)
        for line in ("const icW=Math.max(maxR-X0, 2*PITCH+PAD);", "const x=X0+PAD+170+col*PITCH, yy=y-row*ROWH;"):
            self.assertIn(line, js)                          # same placement code as the labels style


class Policy(unittest.TestCase):
    def test_precedence_and_legacy_default(self):
        self.assertEqual(S.wiring_policy({}), "labels")                                    # existing projects
        self.assertEqual(S.wiring_policy({"wiring": "subsystem"}), "subsystem")
        self.assertEqual(S.wiring_policy({"wiring": "subsystem"}, {"wiring": "labels"}), "labels")   # client rule
        with self.assertRaises(ValueError):
            S.wiring_policy({"wiring": "fancy"})

    def test_new_projects_default_to_subsystem(self):
        with open(os.path.join(ROOT, "templates", "project", "project.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["wiring"], S.NEW_PROJECT_WIRING)
        self.assertEqual(S.NEW_PROJECT_WIRING, "subsystem")

    def test_classify_nets(self):
        c = S.classify_nets(BLOCKS[0], BLOCKS)
        self.assertEqual(c["GND"], "power")
        self.assertEqual(c["+3V3"], "power")
        self.assertEqual(c["VIN_5V"], "power")
        self.assertEqual(c["EN"], "port")
        self.assertEqual(c["FB"], "local")
        self.assertEqual(c["EN_RC"], "local")
        self.assertEqual(c["LINK"], "port")
        c2 = S.classify_nets(BLOCKS[1], BLOCKS, rails=["XI"])
        self.assertEqual(c2["XI"], "power")                  # project.json 'rails'
        self.assertEqual(c2["BTN"], "local")
        nb = copy.deepcopy(BLOCKS[1]); nb["ports"].remove("LINK")
        self.assertEqual(S.classify_nets(nb, [BLOCKS[0], nb])["LINK"], "cross")


class Router(unittest.TestCase):
    def test_both_fixture_blocks_route_cleanly(self):
        for b in BLOCKS:
            _, plan, _ = plans(b)
            res = R.check_plan(plan, b)
            self.assertTrue(res["ok"], f"{b['id']}: " + "\n".join(res["errors"][:20]))
            self.assertEqual(res["crossings"], 0)
            self.assertEqual(plan["fallback"], {}, b["id"])
            for net, info in plan["nets"].items():
                if info["class"] in ("local", "port", "cross") and len(info["pins"]) >= 2:
                    self.assertEqual(info["mode"], "wire", net)
                if info["class"] == "power":
                    self.assertEqual(info["mode"], "label", net)

    def test_wires_are_orthogonal_on_grid_and_inside_window(self):
        for b in BLOCKS:
            _, plan, _ = plans(b)
            x0, y0, x1, y1 = plan["window"]
            for s in plan["segments"]:
                (ax, ay), (bx, by) = s["a"], s["b"]
                self.assertTrue(ax == bx or ay == by, s)
                if plan["nets"][s["net"]]["mode"] == "wire":
                    for v in (ax, ay, bx, by):
                        self.assertEqual(v % R.GRID, 0, s)
                    self.assertTrue(x0 <= min(ax, bx) and max(ax, bx) <= x1 and y0 <= min(ay, by) and max(ay, by) <= y1, s)

    def test_port_net_is_wired_and_labelled_once(self):
        _, plan, _ = plans(BLOCKS[0])
        self.assertEqual(plan["nets"]["EN"]["mode"], "wire")
        self.assertEqual([l["net"] for l in plan["labels"]].count("EN"), 1)
        self.assertEqual([l["net"] for l in plan["labels"]].count("FB"), 0)        # local: wires only
        self.assertEqual([l["net"] for l in plan["labels"]].count("GND"), 5)       # every GND pin labelled

    def test_deterministic(self):
        a = json.dumps(plans(BLOCKS[1])[1], sort_keys=True)
        b = json.dumps(plans(BLOCKS[1])[1], sort_keys=True)
        self.assertEqual(a, b)

    def test_tight_window_falls_back_to_labels_and_stays_correct(self):
        b = BLOCKS[1]
        placed = synthetic_place(b, *ORIGIN[b["id"]])
        xs = [p["x"] for ps in placed["PINS"].values() for p in ps]
        ys = [p["y"] for ps in placed["PINS"].values() for p in ps]
        plan = R.plan_block(b, placed["PINS"], S.classify_nets(b, BLOCKS),
                            (min(xs), min(ys), max(xs), max(ys)), draw.STYLE["stub"])
        self.assertTrue(plan["fallback"])
        for net in plan["fallback"]:
            self.assertEqual(plan["nets"][net]["mode"], "label")
        res = R.check_plan(plan, b)
        self.assertEqual(R.derive_netlist(plan)[0], R.spec_netlist(b))
        self.assertEqual(res["crossings"], 0)

    def test_client_forced_label_nets(self):
        b = copy.deepcopy(BLOCKS[0]); b["label_nets"] = ["FB"]
        placed = synthetic_place(b, 100, 3200)
        plan = draw.plan_subsystem(b, BLOCKS, placed, 100, 3200, {})
        self.assertEqual(plan["nets"]["FB"]["mode"], "label")
        self.assertTrue(R.check_plan(plan, b)["ok"])

    def test_off_grid_pin_falls_back(self):
        b = BLOCKS[0]
        placed = synthetic_place(b, 100, 3200)
        placed["PINS"]["R2"][0]["x"] += 5                    # FB pin of R2 off the 10-unit grid
        plan = draw.plan_subsystem(b, BLOCKS, placed, 100, 3200, {})
        self.assertEqual(plan["nets"]["FB"]["mode"], "label")
        self.assertIn("grid", plan["fallback"]["FB"])
        self.assertEqual(R.derive_netlist(plan)[0], R.spec_netlist(b))


class NetlistEquivalence(unittest.TestCase):
    def test_both_styles_give_the_spec_netlist(self):
        for b in BLOCKS:
            _, sub, lab = plans(b)
            want = R.spec_netlist(b)
            self.assertEqual(R.derive_netlist(sub), (want, []), b["id"])
            self.assertEqual(R.derive_netlist(lab), (want, []), b["id"])
            self.assertTrue(R.check_plan(lab, b)["ok"], R.check_plan(lab, b)["errors"][:5])


class Checker(unittest.TestCase):
    """The checker must catch every defect class on hand-made plans."""

    def base(self):
        return {"segments": [{"net": "A", "a": [0, 0], "b": [100, 0]}],
                "labels": [], "pins": {"U1.1": {"at": [0, 0], "net": "A"}, "U2.1": {"at": [100, 0], "net": "A"}}}

    def errs(self, plan):
        return " | ".join(R.check_plan(plan)["errors"])

    def test_clean(self):
        self.assertTrue(R.check_plan(self.base())["ok"])

    def test_crossing_of_two_nets(self):
        p = self.base()
        p["segments"].append({"net": "B", "a": [50, -50], "b": [50, 50]})
        p["pins"].update({"U3.1": {"at": [50, -50], "net": "B"}, "U4.1": {"at": [50, 50], "net": "B"}})
        r = R.check_plan(p)
        self.assertEqual(r["crossings"], 1)
        self.assertIn("short", self.errs(p))

    def test_overlap_same_net(self):
        p = self.base()
        p["segments"].append({"net": "A", "a": [50, 0], "b": [150, 0]})
        self.assertIn("overlap", self.errs(p))

    def test_t_join_mid_segment(self):
        p = self.base()
        p["segments"].append({"net": "A", "a": [50, 0], "b": [50, 50]})
        p["pins"]["U3.1"] = {"at": [50, 50], "net": "A"}
        self.assertIn("mid-segment", self.errs(p))

    def test_wire_over_foreign_pin_and_open(self):
        p = self.base()
        p["pins"]["U5.1"] = {"at": [50, 0], "net": "B"}
        self.assertIn("touches pin U5.1", self.errs(p))
        self.assertIn("open: pin U5.1", self.errs(p))

    def test_floating_label_and_label_short(self):
        p = self.base()
        p["labels"].append({"net": "A", "at": [200, 200], "rotation": 0})
        self.assertIn("floating label", self.errs(p))
        p = self.base()
        p["labels"].append({"net": "B", "at": [100, 0], "rotation": 0})
        self.assertIn("short", self.errs(p))

    def test_split_net_is_open(self):
        p = {"segments": [], "labels": [], "pins": {"U1.1": {"at": [0, 0], "net": "A"}, "U2.1": {"at": [9, 9], "net": "A"}}}
        p["segments"] = [{"net": "A", "a": [0, 0], "b": [0, 5]}, {"net": "A", "a": [9, 9], "b": [9, 20]}]
        self.assertIn("separate pieces", self.errs(p))

    def test_dangling_and_stray_wires(self):
        p = self.base()
        p["segments"].append({"net": "A", "a": [100, 0], "b": [100, 80]})          # stub to nowhere
        self.assertIn("dangling", self.errs(p))
        p = self.base()
        p["segments"].append({"net": "A", "a": [0, 500], "b": [300, 500]})         # isolated stray wire
        self.assertIn("dangling", self.errs(p))

    def test_spec_mismatch(self):
        self.assertIn("netlist", " ".join(R.check_plan(self.base(), {"parts": [{"ref": "U1", "pins": {"1": "A"}}]})["errors"]))

    def test_wire_under_symbol_and_text_overlaps(self):
        p = self.base()
        p["bodies"] = {"U9": [40, -20, 60, 20]}
        self.assertIn("under symbol U9", self.errs(p))
        p = self.base()
        p["bodies"] = {"U8": [0, 10, 20, 30], "U9": [10, 20, 40, 40]}
        self.assertIn("symbols U8 and U9 overlap", self.errs(p))
        p = self.base()
        p["labels"] = [{"net": "A", "at": [100, 0], "rotation": 0, "dir": [1, 0]},
                       {"net": "A", "at": [100, 0], "rotation": 0, "dir": [1, 0]}]
        self.assertIn("labels A", self.errs(p))

    def test_missing_and_extra_junction_dots(self):
        p = self.base()
        p["segments"] = [{"net": "A", "a": [0, 0], "b": [50, 0]}, {"net": "A", "a": [50, 0], "b": [100, 0]},
                         {"net": "A", "a": [50, 0], "b": [50, 50]}]
        p["pins"]["U3.1"] = {"at": [50, 50], "net": "A"}
        p["junctions"] = []
        self.assertIn("no junction dot", self.errs(p))
        p["junctions"] = [{"net": "A", "at": [50, 0]}, {"net": "A", "at": [0, 0]}]
        self.assertIn("fewer than three", self.errs(p))


class StyleAndAdapter(unittest.TestCase):
    def test_every_t_junction_has_a_dot(self):
        seen = 0
        for b in BLOCKS:
            _, plan, _ = plans(b)
            ends = {}
            for s in plan["segments"]:
                for p in (s["a"], s["b"]):
                    ends[(s["net"], tuple(p))] = ends.get((s["net"], tuple(p)), 0) + 1
            want = sorted([n, list(p)] for (n, p), d in ends.items() if d >= 3)
            self.assertEqual(sorted([j["net"], j["at"]] for j in plan["junctions"]), want)
            seen += len(want)
        self.assertGreater(seen, 0, "fixtures must exercise at least one T-junction")

    def test_style_table_is_complete_and_colours_are_as_specified(self):
        st = draw.SUBSYSTEM_STYLE
        self.assertEqual(set(st), set(draw.SUBSYSTEM_STYLE_APPLIED), "every style key says how it is applied")
        rgb = lambda h: tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))  # noqa: E731
        self.assertEqual(rgb(st["background"]), (255, 255, 255))
        g = rgb(st["wire_color"]); self.assertTrue(g[1] > g[0] and g[1] > g[2], "wires are green")
        for k in ("label_color", "reference_color", "frame_color", "title_color"):
            c = rgb(st[k]); self.assertTrue(c[2] > c[0] and c[2] > c[1], f"{k} is blue / dark blue")
        self.assertLessEqual(max(rgb(st["ground_color"])), 0x40, "ground is black / dark")
        self.assertTrue(st["junction_dots"])
        self.assertEqual(draw.STYLE["label_size"], st["label_size"])

    def test_draw_js_uses_the_style_table(self):
        _, plan, _ = plans(BLOCKS[0])
        st = dict(draw.SUBSYSTEM_STYLE, wire_color="#00AA11", label_color="#2233CC", ground_color="#111111")
        js = subsystem_draw_js(plan, st)
        for v in ("#00AA11", "#2233CC", "#111111", st["frame_color"], st["title_color"]):
            self.assertIn(v, js)
        payload = json.loads(js.split("const P=", 1)[1].split("; let SF", 1)[0])
        self.assertEqual(len(payload["w"]), len(plan["segments"]))
        self.assertEqual(len(payload["j"]), len(plan["junctions"]))
        gnd = [l for l in payload["l"] if l[3] == "GND"]
        self.assertTrue(gnd and all(l[4] == "#111111" for l in gnd))
        self.assertTrue(all(l[4] == "#2233CC" for l in payload["l"] if l[3] != "GND"))
        self.assertEqual(json.loads(js.split("const S=", 1)[1].split("; const P=", 1)[0])["wire_color"], "#00AA11")

    def test_draw_js_snapshot(self):
        for b in BLOCKS:
            _, plan, _ = plans(b)
            js = subsystem_draw_js(plan, draw.SUBSYSTEM_STYLE)
            path = os.path.join(FX_DIR, f"subsystem_{b['id']}.golden.js")
            if os.environ.get("DESK_UPDATE_GOLDEN") == "1":
                with open(path, "w", encoding="utf-8", newline="\n") as f:
                    f.write(js)
            with open(path, encoding="utf-8") as f:
                self.assertEqual(js, f.read().replace("\r\n", "\n"), f"{b['id']}: re-run with DESK_UPDATE_GOLDEN=1 "
                                                                       "only for an intended change")

    def test_svg_preview_snapshot(self):
        """Visual regression: the deterministic SVG preview of each fixture plan matches its golden file."""
        for b in BLOCKS:
            _, plan, _ = plans(b)
            svg = draw.plan_svg(plan)
            self.assertIn(draw.SUBSYSTEM_STYLE["wire_color"], svg)
            self.assertEqual(svg.count("<circle"), len(plan["junctions"]))
            self.assertEqual(svg.count("<line"), len(plan["segments"]))
            path = os.path.join(FX_DIR, f"subsystem_{b['id']}.golden.svg")
            if os.environ.get("DESK_UPDATE_GOLDEN") == "1":
                with open(path, "w", encoding="utf-8", newline="\n") as f:
                    f.write(svg)
            with open(path, encoding="utf-8") as f:
                self.assertEqual(svg, f.read().replace("\r\n", "\n"), b["id"])

    def test_connectivity_calls_are_not_wrapped_style_calls_are(self):
        _, plan, _ = plans(BLOCKS[0])
        js = subsystem_draw_js(plan, draw.SUBSYSTEM_STYLE)
        self.assertIn("{const w=await eda.sch_PrimitiveWire.create(", js)
        self.assertIn("try{await eda.sch_PrimitiveWire.modify(", js)
        self.assertIn("try{await eda.sch_PrimitiveCircle.create(", js)
        self.assertIn("wire_style", UNVERIFIED_LIVE)
        self.assertIn("wire_network", UNVERIFIED_LIVE)

    def test_page_creation_refuses(self):
        with self.assertRaises(NotImplementedError):
            create_sheet_js("POWER")

    def test_frame_encloses_wires_and_labels(self):
        for b in BLOCKS:
            _, plan, _ = plans(b)
            x, yt, W, H = plan["frame"]
            for s in plan["segments"]:
                for px, py in (s["a"], s["b"]):
                    self.assertTrue(x <= px <= x + W and yt - H <= py <= yt, (s, plan["frame"]))


class Sheets(unittest.TestCase):
    PJ = {"sheet_uuid": "legacy", "sheets": [{"id": "PWR", "uuid": "u-pwr", "blocks": ["01_SYN_REG"]},
                                             {"id": "MCU", "blocks": ["02_SYN_MCU"]}]}

    def test_sheet_selection(self):
        self.assertEqual(S.sheet_uuid_for({"sheet_uuid": "only"}, ["01_SYN_REG"]), "only")
        self.assertEqual(S.sheet_uuid_for(self.PJ, ["01_SYN_REG"]), "u-pwr")
        with self.assertRaises(ValueError):
            S.sheet_uuid_for(self.PJ, ["02_SYN_MCU"])           # no uuid yet: page creation is UNVERIFIED-LIVE
        with self.assertRaises(ValueError):
            S.sheet_uuid_for(self.PJ, ["01_SYN_REG", "02_SYN_MCU"])

    def test_cross_sheet_ports_and_lint(self):
        self.assertEqual(S.cross_sheet_ports(self.PJ, BLOCKS), {"LINK": ["MCU", "PWR"]})
        E, _ = S.lint_project_model(self.PJ, BLOCKS)
        self.assertEqual(E, [])
        nb = copy.deepcopy(BLOCKS); nb[1]["ports"].remove("LINK")
        E, _ = S.lint_project_model(self.PJ, nb)
        self.assertTrue(any("LINK crosses sheets" in e for e in E), E)
        bad = {"sheets": [{"id": "A", "blocks": ["01_SYN_REG", "NOPE"]}], "wiring": "pretty"}
        E, _ = S.lint_project_model(bad, BLOCKS)
        self.assertTrue(any("NOPE" in e for e in E) and any("no sheet" in e for e in E) and any("pretty" in e for e in E), E)


class VerifySavedPlans(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="desk_ver_")
        os.makedirs(os.path.join(self.tmp, "state", "wiring"))
        self.b = BLOCKS[0]
        _, self.plan, _ = plans(self.b)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def save(self, plan):
        with open(os.path.join(self.tmp, "state", "wiring", self.b["id"] + ".json"), "w", encoding="utf-8") as f:
            json.dump(plan, f)

    def test_labels_built_block_needs_no_plan(self):
        E, notes = R.check_saved_plans(self.tmp, BLOCKS, {self.b["id"]}, {self.b["id"]: {}}, {})
        self.assertEqual(E, [])
        E, notes = R.check_saved_plans(self.tmp, BLOCKS, {self.b["id"]}, {self.b["id"]: {}}, {"wiring": "subsystem"})
        self.assertEqual(E, [])
        self.assertTrue(any("clear_block + build" in n for n in notes))      # migrated, not yet redrawn: reported, not failed

    def test_subsystem_block_needs_a_clean_plan(self):
        lay = {self.b["id"]: {"wiring": "subsystem"}}
        E, _ = R.check_saved_plans(self.tmp, BLOCKS, {self.b["id"]}, lay, {"wiring": "subsystem"})
        self.assertTrue(any("missing" in e for e in E))          # fail closed without the plan
        self.save(self.plan)
        E, notes = R.check_saved_plans(self.tmp, BLOCKS, {self.b["id"]}, lay, {"wiring": "subsystem"})
        self.assertEqual(E, [])
        bad = copy.deepcopy(self.plan)
        bad["segments"].append({"net": "FB", "a": [0, 0], "b": [5000, 0]})
        self.save(bad)
        E, _ = R.check_saved_plans(self.tmp, BLOCKS, {self.b["id"]}, lay, {"wiring": "subsystem"})
        self.assertTrue(E)
        changed = copy.deepcopy(BLOCKS); changed[0]["parts"][1]["pins"]["1"] = "EN"     # spec edited after build
        self.save(self.plan)
        E, _ = R.check_saved_plans(self.tmp, changed, {self.b["id"]}, lay, {"wiring": "subsystem"})
        self.assertTrue(any("netlist" in e for e in E))


class BuildAndVerifyWithMockBridge(unittest.TestCase):
    """tools/build.py (subsystem) then tools/verify.py, end to end, against a FAKE bridge that records the scripts
    and answers like a sheet that honours every wire's net (the UNVERIFIED-LIVE assumption). No EasyEDA, no real
    project: a temp copy of the synthetic fixture."""

    def setUp(self):
        import types
        from unittest import mock
        self.tmp = tempfile.mkdtemp(prefix="desk_bv_")
        self.p = os.path.join(self.tmp, "SYN")
        os.makedirs(os.path.join(self.p, "blocks"))
        for b in BLOCKS:
            with open(os.path.join(self.p, "blocks", b["id"] + ".json"), "w", encoding="utf-8") as f:
                json.dump(b, f)
        with open(os.path.join(self.p, "project.json"), "w", encoding="utf-8") as f:
            json.dump({"name": "SYN", "sheet_uuid": "sheet-syn", "pcb_uuid": "pcb-syn", "wiring": "subsystem"}, f)
        self.scripts = []
        fake = types.ModuleType("_common")
        fake.ex = self.fake_ex
        fake.guard = lambda uuid, open_doc=True: f"/*guard {uuid}*/"
        fake.check = lambda r: r
        fake.load_project = lambda p: json.load(open(os.path.join(p, "project.json"), encoding="utf-8"))
        fake.S = S
        self.patches = [mock.patch.dict(sys.modules, {"_common": fake}),
                        mock.patch.object(S, "lint", lambda *a, **k: ([], [])),
                        mock.patch.object(S, "load_library", lambda: FX["library"]),
                        mock.patch.object(S, "load_pins", lambda m: [{"num": str(i)} for i in range(FX["pin_counts"][m])])]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def fake_ex(self, js, **kw):
        self.scripts.append(js)
        if "return cs.map(c=>c.getState_Designator())" in js:
            return []
        if "return {W,H,REF,PINS};" in js:
            spec = json.loads(js.split("const SPEC=", 1)[1].split("; const X0=", 1)[0])
            x0 = int(js.split("const X0=", 1)[1].split(",", 1)[0]); yt = int(js.split("YT=", 1)[1].split(";", 1)[0])
            block = next(b for b in BLOCKS if b["title"] == spec["title"])
            return synthetic_place(block, x0, yt)
        if "for(const s of P.w)" in js:
            return {"wires": 1}
        if 'getNetlist("Protel2")' in js:            # a sheet whose wires carry their net names
            parts = [{"ref": p["ref"], "dev": FX["library"][p["mpn"]]["name"],
                      "pins": [{"num": n, "name": n, "net": net, "nc": False} for n, net in p["pins"].items()] +
                              [{"num": n, "name": n, "net": None, "nc": True} for n in p.get("nc", [])]}
                     for b in BLOCKS for p in b["parts"]]
            return {"nl": "", "parts": parts}
        raise AssertionError("unexpected script: " + js[:120])

    def run_tool(self, name, *argv):
        import contextlib
        import io
        import runpy
        old = sys.argv
        sys.argv = [os.path.join(ROOT, "tools", name + ".py"), *argv]
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                runpy.run_path(sys.argv[0], run_name="__main__")
            return 0
        except SystemExit as e:
            return e.code
        finally:
            sys.argv = old

    def test_build_then_verify(self):
        for b in BLOCKS:
            self.assertIn(self.run_tool("build", self.p, b["id"]), (0, None))
            plan_file = os.path.join(self.p, "state", "wiring", b["id"] + ".json")
            with open(plan_file, encoding="utf-8") as f:
                plan = json.load(f)
            self.assertTrue(plan["check"]["ok"], plan["check"]["errors"][:5])
            self.assertTrue(any(v["mode"] == "wire" for v in plan["nets"].values()))
        draws = [s for s in self.scripts if "for(const s of P.w)" in s]
        self.assertEqual(len(draws), 2)
        self.assertTrue(all("/*guard sheet-syn*/" in s for s in draws))
        with open(os.path.join(self.p, "state", "layout.json"), encoding="utf-8") as f:
            lay = json.load(f)["blocks"]
        self.assertEqual({v["wiring"] for v in lay.values()}, {"subsystem"})
        b0, b1 = lay["01_SYN_REG"], lay["02_SYN_MCU"]
        self.assertGreaterEqual(b1["x"], b0["x"] + b0["W"])           # blocks do not overlap
        self.assertEqual(self.run_tool("verify", self.p), 0)
        # a tampered plan makes verify fail closed even though the netlist matches
        pf = os.path.join(self.p, "state", "wiring", "01_SYN_REG.json")
        with open(pf, encoding="utf-8") as f:
            plan = json.load(f)
        plan["segments"].append({"net": "FB", "a": [0, 0], "b": [10, 0]})
        with open(pf, "w", encoding="utf-8") as f:
            json.dump(plan, f)
        self.assertEqual(self.run_tool("verify", self.p), 1)


def _load_tool(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "tools", name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Migration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="desk_mig_")
        self.p = os.path.join(self.tmp, "SYN")
        os.makedirs(os.path.join(self.p, "blocks"))
        os.makedirs(os.path.join(self.p, "state"))
        for b in BLOCKS:
            with open(os.path.join(self.p, "blocks", b["id"] + ".json"), "w", encoding="utf-8") as f:
                json.dump(b, f)
        self.pj = {"name": "SYN", "sheet_uuid": "s", "pcb_uuid": "p"}
        with open(os.path.join(self.p, "project.json"), "w", encoding="utf-8") as f:
            json.dump(self.pj, f)
        with open(os.path.join(self.p, "state", "layout.json"), "w", encoding="utf-8") as f:
            json.dump({"cursor": [0, 0], "row_h": 0, "blocks": {"01_SYN_REG": {"x": 100, "y": 3200, "W": 1, "H": 1}}}, f)
        self.mig = _load_tool("migrate_wiring")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def read_pj(self):
        with open(os.path.join(self.p, "project.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_preview_changes_nothing(self):
        with open(os.path.join(self.p, "project.json"), "rb") as f:
            before = f.read()
        prev = self.mig.preview(self.p)
        with open(os.path.join(self.p, "project.json"), "rb") as f:
            self.assertEqual(f.read(), before)
        self.assertEqual(prev["from"], "labels")
        self.assertEqual(prev["to"], "subsystem")
        self.assertTrue(prev["blocks"]["01_SYN_REG"]["built"])
        self.assertIn("FB", prev["blocks"]["01_SYN_REG"]["wired_nets"])
        self.assertIn("01_SYN_REG", prev["rebuild_needed"])
        self.assertTrue(os.path.exists(os.path.join(self.p, "state", "wiring_migration_preview.json")))

    def test_apply_requires_matching_preview_and_backs_up(self):
        with self.assertRaises(SystemExit):
            self.mig.apply(self.p, "0" * 12)                     # no / wrong preview
        prev = self.mig.preview(self.p)
        res = self.mig.apply(self.p, prev["token"])
        self.assertEqual(self.read_pj()["wiring"], "subsystem")
        with open(res["backup"], encoding="utf-8") as f:
            self.assertEqual(json.load(f), self.pj)
        with open(os.path.join(self.p, "state", "layout.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["blocks"]["01_SYN_REG"], {"x": 100, "y": 3200, "W": 1, "H": 1})

    def test_stale_preview_is_refused(self):
        prev = self.mig.preview(self.p)
        b = copy.deepcopy(BLOCKS[0]); b["ports"].append("FB")
        with open(os.path.join(self.p, "blocks", b["id"] + ".json"), "w", encoding="utf-8") as f:
            json.dump(b, f)
        with self.assertRaises(SystemExit):
            self.mig.apply(self.p, prev["token"])
        self.assertNotIn("wiring", self.read_pj())


if __name__ == "__main__":
    unittest.main()
