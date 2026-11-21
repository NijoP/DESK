"""Roadmap increment I-2, engineering-data correctness: one reference-value test per finding (E-2..E-10) plus the
rotated pad / bbox geometry. Each test is built from the reproduction in the DESK audit and checks the correct value.
E-1 (creepage table) is excluded: its source column is an open owner decision (D-5)."""
import math
import os
import shutil
import tempfile
import unittest
import zipfile

from desk import calc
from desk import ipc
from desk import spacing as SP
from desk import release as RL
from desk.profile import DesignProfile, LayerStackup
from desk.routability import RoutabilityEvaluator
from desk.router import DSNTuningEngine, RoutingPlanGenerator, TraceWidthCalculator
from desk.routing import feasibility as FZ
from desk.routing.connectivity import PhysicalConnectivityVerifier
from desk.routing.dsn import DSNInvariantViolationError, DSNTree, SExprParser
from desk.routing.padgeom import make_shape, pad_gap, pad_shape, segment_to_pad_distance
from desk.routing.width import TraceWidthManager, plan_board_widening, widening_shortfall
from desk.snapshot import IndexedPCBSnapshot

MIL = 39.37007874


def _pad(num, dx, dy, w, h, net, rot=0, layer=1):
    return {"num": str(num), "dx": dx, "dy": dy, "shape": ["RECT", w, h, 0], "rot": rot, "net": net, "layer": layer}


class TestE1CreepageColumn(unittest.TestCase):
    """Owner decision: the conservative material-group column everywhere, provisional and unverified."""

    def test_curve_is_monotone_and_has_no_40v_cliff(self):
        for pd, groups in ((1, ("III",)), (2, ("I", "II", "III", "IIIa", "IIIb"))):
            for mg in groups:
                prev = 0.0
                for tenth in range(0, 10001):
                    c = ipc.creepage_mm(tenth / 10.0, pd, mg)
                    self.assertGreaterEqual(c, prev, f"PD{pd} {mg} at {tenth / 10.0} V")
                    prev = c
        self.assertEqual(ipc.creepage_mm(40, 2, "III"), ipc.creepage_mm(41, 2, "III"))
        self.assertEqual(ipc.creepage_mm(40, 2, "III"), 1.2)          # the 50 V row of the same column, not 0.04

    def test_values_stay_labelled_unverified(self):
        self.assertFalse(ipc.verified_against_standard)
        self.assertIn("UNVERIFIED", ipc.CREEPAGE_BASIS)
        req = SP.requirement("A", "B", 48.0, 0.0, "B2", 0.1, SP.SpacingPolicy.CREEPAGE_AS_CLEARANCE)
        self.assertEqual(req.to_dict()["creepage_basis"], ipc.CREEPAGE_BASIS)
        self.assertFalse(req.to_dict()["table_verified"])


class TestE2PairwiseClearance(unittest.TestCase):
    """VP = +170 V and VN = -170 V: each is 170 V from GND but 340 V from the other."""

    def _profile(self, policy):
        return DesignProfile("t", voltage_rails={"VP": 170.0, "VN": -170.0, "GND": 0.0}, spacing_policy=policy)

    def test_worst_pair_is_vp_to_vn_at_340v(self):
        # IPC-2221B Table 6-1 B2: 151-300 V -> 1.25 mm (49.21 mil), 301-500 V -> 2.5 mm (98.43 mil)
        p = self._profile("FUNCTIONAL")
        self.assertAlmostEqual(p.derive_clearance_mil("VP", "GND"), 49.21, places=2)
        rule, partner, skipped = p.worst_case_clearance_mil("VP", ["VP", "VN", "GND"])
        self.assertAlmostEqual(rule, 98.43, places=2)
        self.assertEqual((partner, skipped), ("VN", []))

    def test_routing_plan_uses_the_worst_pair(self):
        for policy in ("FUNCTIONAL", "CREEPAGE_AS_CLEARANCE"):
            p = self._profile(policy)
            dump = {"Q1": {"x": 0, "y": 0, "rot": 0, "layer": 1,
                           "pads": [_pad(1, 0, 0, 40, 40, "VP"), _pad(2, 400, 0, 40, 40, "VN"), _pad(3, 800, 0, 40, 40, "GND")]},
                    "Q2": {"x": 0, "y": 1000, "rot": 0, "layer": 1,
                           "pads": [_pad(1, 0, 0, 40, 40, "VP"), _pad(2, 400, 0, 40, 40, "VN"), _pad(3, 800, 0, 40, 40, "GND")]}}
            graph = RoutabilityEvaluator.build_connectivity_graph(dump)
            plan = RoutingPlanGenerator.generate_plan(graph, dump, (50.0, 50.0), profile=p)
            pair = p.derive_clearance_mil("VP", "VN")
            self.assertGreater(pair, p.derive_clearance_mil("VP", "GND"))
            self.assertAlmostEqual(plan.net_constraints["VP"].clearance_mil, pair, places=6, msg=policy)
            self.assertAlmostEqual(plan.net_constraints["VN"].clearance_mil, pair, places=6, msg=policy)
            # GND sits 170 V from either rail: its own rule is the 170 V rule, never less than before
            self.assertAlmostEqual(plan.net_constraints["GND"].clearance_mil, p.derive_clearance_mil("GND", "VP"), places=6)


class TestE3Widening(unittest.TestCase):
    def test_widening_next_to_a_neighbour_keeps_the_real_gap(self):
        # 10 -> 50 mil next to a 10 mil track 30 mil away (centre to centre): the old test approved 50 mil (0 mil gap)
        seg = [{"id": "s", "start_x": 0, "start_y": 0, "end_x": 500, "end_y": 0, "width": 10, "layer": 1}]
        plan = TraceWidthManager.plan_power_widening("VIN", seg, 50.0, obstacles=[(0, 30, 500, 30, 1, 10.0)],
                                                     min_clearance_mil=5.0)
        c = plan.candidates[0]
        self.assertEqual(c.approved_width_mil, 40.0)                        # 30 - 10/2 - 5 = 20 half-width
        self.assertAlmostEqual(30 - 10 / 2 - c.approved_width_mil / 2, 5.0)   # real copper gap = the rule
        self.assertAlmostEqual(c.min_observed_clearance_mil, 5.0)

    def test_crossing_obstacle_is_not_missed(self):
        # The old endpoint-only distance saw a crossing track as 250 mil away
        seg = [{"id": "s", "start_x": 0, "start_y": 0, "end_x": 500, "end_y": 0, "width": 10, "layer": 1}]
        plan = TraceWidthManager.plan_power_widening("VIN", seg, 50.0, obstacles=[(250, -300, 250, 300, 1, 10.0)],
                                                     min_clearance_mil=5.0)
        self.assertFalse(plan.candidates[0].is_widened)

    def test_board_plan_sees_other_power_nets_pads_and_their_rules(self):
        lines = [{"id": "a", "net": "VA", "start_x": 0, "start_y": 0, "end_x": 600, "end_y": 0, "width": 10, "layer": 1},
                 {"id": "b", "net": "VB", "start_x": 0, "start_y": 50, "end_x": 600, "end_y": 50, "width": 10, "layer": 1}]
        plans = plan_board_widening({"VA": 50.0, "VB": 50.0}, lines, net_clearances_mil={"VA": 5.0, "VB": 5.0})
        wa = plans["VA"].candidates[0].approved_width_mil
        wb = plans["VB"].candidates[0].approved_width_mil
        self.assertEqual((wa, wb), (50.0, 40.0))                           # VB yields to the already widened VA
        self.assertGreaterEqual(50 - wa / 2 - wb / 2, 5.0 - 1e-6)            # the two trunks never meet
        self.assertEqual(set(widening_shortfall(plans)), {"VB"})
        # a high-voltage neighbour's own rule applies, not the widened net's
        dump = {"U1": {"x": 300, "y": 80, "rot": 0, "layer": 1, "pads": [_pad(1, 0, 0, 20, 20, "HV")]}}
        plans = plan_board_widening({"VA": 50.0}, lines[:1], pcb_dump=dump, net_clearances_mil={"VA": 5.0, "HV": 60.0})
        # enclosing-circle pad edge 80 - 14.14 = 65.86 mil; minus the 60 mil HV rule leaves a 5.86 mil half-width
        self.assertEqual(plans["VA"].candidates[0].approved_width_mil, 11.7)


class TestE4FallbackTuner(unittest.TestCase):
    def test_lost_per_net_clearance_raises(self):
        # Unparsable fragment with an unquoted class member: the regex fallback cannot apply the HV rule
        frag = "(boundary (path signal 0 0 0 0 100 100))\n(rule (width 5.0))\n(class HV VBULK (rule (width 5.0) (clearance 4.02)))"
        with self.assertRaises(DSNInvariantViolationError) as cm:
            DSNTuningEngine.tune_dsn(frag, (1000.0, 1000.0), net_clearances={"HV": 60.0})
        self.assertIn("HV", str(cm.exception))

    def test_applied_fallback_still_works(self):
        frag = "(boundary (path signal 0 0 0 0 100 100))\n(rule (width 5.0))\n(class PWR 'VIN' (rule (width 5.0) (clearance 4.02)))"
        out = DSNTuningEngine.tune_dsn(frag, (1000.0, 1000.0), net_widths={"PWR": 20.0}, net_clearances={"PWR": 8.0})
        self.assertIn("(clearance 8.0)", out)


class TestE5Connectivity(unittest.TestCase):
    def _dump(self, rot):
        return {"U1": {"x": 0, "y": 0, "rot": rot, "layer": 1,
                       "pads": [_pad(1, 0, 0, 80, 20, "A", rot=rot), _pad(2, 500, 0, 20, 20, "A")]}}

    def _tracks(self, y_end):
        return [{"net": "A", "start_x": 0, "start_y": y_end, "end_x": 500, "end_y": y_end, "width": 10, "layer": 1},
                {"net": "A", "start_x": 500, "start_y": y_end, "end_x": 500, "end_y": 0, "width": 10, "layer": 1}]

    def test_track_stopping_short_of_an_80x20_pad_is_not_connected(self):
        # Centreline at y=45: copper edge 40 vs pad edge 10 -> 30 mil gap. The circle model (r = 40) said connected.
        r = PhysicalConnectivityVerifier.verify_board(self._dump(0), self._tracks(45))
        self.assertFalse(r.is_100_percent_routed)
        self.assertEqual(r.net_reports["A"].unconnected_pads, ["U1.1"])

    def test_track_touching_the_pad_edge_is_connected(self):
        r = PhysicalConnectivityVerifier.verify_board(self._dump(0), self._tracks(15))
        self.assertTrue(r.is_100_percent_routed)

    def test_rotated_pad_reaches_the_track(self):
        # Turned 90 deg the same pad spans y = -40..40, so the y=45 track (edge at 40) touches it
        r = PhysicalConnectivityVerifier.verify_board(self._dump(90), self._tracks(45))
        self.assertTrue(r.is_100_percent_routed)

    def test_declared_plane_is_not_copper_without_it(self):
        dump = {"U1": {"x": 0, "y": 0, "rot": 0, "layer": 1, "pads": [_pad(1, 0, 0, 20, 20, "GND"), _pad(2, 500, 0, 20, 20, "GND")]}}
        zone = [{"net": "GND", "layer": 1, "polygon": [[-50, -50], [600, -50], [600, 50], [-50, 50]]}]
        self.assertTrue(PhysicalConnectivityVerifier.verify_board(dump, [], zones=zone).is_100_percent_routed)
        self.assertFalse(PhysicalConnectivityVerifier.verify_board(dump, []).is_100_percent_routed)


class TestE6FailClosedDefaults(unittest.TestCase):
    def test_rail_names_need_declarations(self):
        p = DesignProfile("t")
        issues = p.validate_electrical_inputs(["+48V", "24V", "VPACK", "BAT+"])
        for net in ("+48V", "24V", "VPACK", "BAT+"):
            self.assertTrue(any(i.startswith(net + ": power rail") for i in issues), net)
            self.assertTrue(any(i.startswith(net + ": high-voltage") for i in issues), net)
        self.assertEqual(p.validate_electrical_inputs(["SDA", "LED_K"]), [])
        # a name stating <= 15 V is estimated at that voltage, not at 3.3 V
        self.assertEqual(p.get_net_voltage_status("5V"), (5.0, "ESTIMATED"))
        self.assertEqual(p.get_net_voltage_status("VIN 12V"), (12.0, "ESTIMATED"))
        self.assertEqual(DesignProfile.name_voltage("3V3"), 3.3)
        self.assertEqual(DesignProfile.name_voltage("-15V"), -15.0)

    def test_inner_layer_is_found_by_position_and_low_currents_are_sized(self):
        p = DesignProfile("t", layer_count=4, current_limits_A={"X": 0.3})
        p.stackup = [LayerStackup(1, "F.Cu", "signal"), LayerStackup(2, "In1.Cu", "signal", copper_thickness_oz=0.5),
                     LayerStackup(3, "In2.Cu", "signal", copper_thickness_oz=0.5), LayerStackup(4, "B.Cu", "signal")]
        self.assertTrue(p.is_inner_layer(2) and not p.is_inner_layer(1) and not p.is_inner_layer(4))
        # IPC-2221: 0.3 A, 10 C rise, 0.5 oz internal -> A = (0.3 / (0.024 * 10^0.44))^(1/0.725) = 8.05 mil^2 -> 11.8 mil
        self.assertAlmostEqual(p.derive_trace_width_mil("X", layer_idx=2), 11.8, places=1)
        self.assertEqual(p.derive_trace_width_mil("X", layer_idx=1), p.manufacturing.min_trace_width_mil)
        self.assertAlmostEqual(TraceWidthCalculator.get_width_mil("X", current_A=0.3, is_inner=True), 11.8, places=1)
        self.assertEqual(TraceWidthCalculator.get_width_mil("SDA"), 5.0)


class TestE7Units(unittest.TestCase):
    def test_spaced_units(self):
        self.assertAlmostEqual(calc.parse_value("4.7 uF"), 4.7e-6, places=15)
        self.assertEqual(calc.parse_value("562 k"), 562000.0)
        self.assertEqual(calc.parse_value("1 M"), 1e6)
        self.assertAlmostEqual(calc.parse_value("100 nF 50V"), 1e-7, places=15)
        self.assertAlmostEqual(calc.parse_value("10uF 25V"), 1e-5, places=15)   # rating is not part of the value
        self.assertEqual(calc.parse_value("10 25V"), 10.0)
        self.assertIsNone(calc.parse_value("green LED"))

    def test_qa_formula_uses_the_scaled_value(self):
        block = {"parts": [{"ref": "R1", "value": "562 k"}, {"ref": "R2", "value": "100 k"}],
                 "qa": [{"item": "Vout", "expr": "0.6*(1+R1/R2)", "min": 3.9, "max": 4.0}]}
        (_, v, ok, _), = calc.check_qa(block)
        self.assertAlmostEqual(v, 3.972, places=3)
        self.assertTrue(ok)


class TestE8DsnQuoting(unittest.TestCase):
    DSN = ('(pcb t (parser (string_quote ") (space_in_quoted_tokens on)) (structure (layer F.Cu (type signal)) '
           '(rule (width 5) (clear 4))) (placement (component X (place U1 0 0 front 0))) (library) '
           '(network (net "VIN 12V" (pins U1-1)) (class "PWR" "VIN 12V" GND (circuit (use_via v)) (rule (width 5) (clear 4)))))')

    def test_net_with_space_stays_one_member(self):
        tree = DSNTree(self.DSN)
        tree.update_net_classes({"PWR": 20.0}, {"PWR": 30.0}, set())
        out = tree.serialize()
        self.assertIn('(class PWR "VIN 12V" GND', out)
        self.assertIn("(rule (width 20.00) (clear 30.00))", out)
        self.assertIn('(string_quote ")', out)
        cls = [n for n in SExprParser.parse(out)[6][1:] if isinstance(n, list) and n[0] == "class"][0]
        self.assertEqual([m for m in cls[1:] if isinstance(m, str)], ["PWR", '"VIN 12V"', "GND"])


class TestE9Feasibility(unittest.TestCase):
    def test_package_internal_conflict_is_not_hidden_by_a_closer_foreign_pad(self):
        # U1.1 (HV, rule 100 mil) is 60 mil from its own U1.2 and 50 mil from R1.1 of another part
        dump = {"U1": {"x": 0, "y": 0, "rot": 0, "layer": 1,
                       "pads": [_pad(1, 0, 0, 20, 20, "HV"), _pad(2, 80, 0, 20, 20, "GND")]},
                "R1": {"x": 0, "y": 70, "rot": 0, "layer": 1, "pads": [_pad(1, 0, 0, 20, 20, "SIG")]}}
        rep = FZ.evaluate(dump, {"HV": 100.0}, 4.0)
        u1 = [b for b in rep.blocked if b.pad_id == "U1.1"][0]
        self.assertEqual(u1.classification, "BLOCKED_BY_CLEARANCE")
        self.assertEqual(u1.neighbour, "U1.2")
        self.assertFalse(rep.feasible)


class TestRotatedPadGeometry(unittest.TestCase):
    def test_90_degree_rotated_pad_gap(self):
        # Two 80x20 pads 40 mil apart in x: unrotated they overlap, turned 90 deg there is 20 mil of gap
        a0, b0 = make_shape(0, 0, 80, 20, 0), make_shape(40, 0, 80, 20, 0)
        a9, b9 = make_shape(0, 0, 80, 20, 90), make_shape(40, 0, 80, 20, 90)
        self.assertEqual(pad_gap(a0, b0), 0.0)
        self.assertAlmostEqual(pad_gap(a9, b9), 20.0, places=9)
        comp = {"x": 0, "y": 0, "rot": 90, "layer": 1, "pads": [_pad(1, 0, 0, 80, 20, "A", rot=90), _pad(2, 40, 0, 80, 20, "B", rot=90)]}
        pads = FZ._pads({"U1": comp}, (0.0, 0.0))
        self.assertEqual((pads[0].w, pads[0].h), (20.0, 80.0))
        self.assertAlmostEqual(FZ.rect_gap_mil(pads[0], pads[1]), 20.0, places=9)
        # a pad without its own rot takes the component's rotation
        g = pad_shape(comp, {"num": "1", "dx": 0, "dy": 0, "shape": ["RECT", 80, 20, 0], "net": "A"})
        self.assertEqual(tuple(round(v, 9) for v in g.extent()), (20.0, 80.0))

    def test_45_degree_pad_distance(self):
        g = make_shape(0, 0, 20, 20, 45)                       # diamond with corners at +-14.142 on the axes
        self.assertAlmostEqual(segment_to_pad_distance(30, -100, 30, 100, g), 30 - 10 * math.sqrt(2), places=6)

    def test_snapshot_rotation_moves_pads_and_bbox(self):
        dump = {"U1": {"id": "U1", "x": 0, "y": 0, "rot": 0, "layer": 1, "bbox": [-50, 50, -10, 10],
                       "pads": [_pad(1, 40, 0, 20, 20, "A"), _pad(2, -40, 0, 20, 20, "B")]},
                "U2": {"id": "U2", "x": 500, "y": 0, "rot": 0, "layer": 1, "bbox": [-10, 10, -10, 10],
                       "pads": [_pad(1, 0, 0, 20, 20, "A"), _pad(2, 0, 30, 20, 20, "B")]}}
        snap = IndexedPCBSnapshot(dump)
        snap.update_component_placement("U1", 100.0, 100.0, 90.0, 1)
        ep = [e for e in snap.net_to_endpoints["A"] if e.ref == "U1"][0]
        self.assertAlmostEqual(ep.x_mil, 100.0, places=9)
        self.assertAlmostEqual(ep.y_mil, 140.0, places=9)
        self.assertEqual([round(v, 9) for v in dump["U1"]["bbox"]], [-10.0, 10.0, -50.0, 50.0])
        self.assertEqual(dump["U1"]["pads"][0]["rot"], 90.0)
        # a second rotation is again a delta from the stored state
        snap.update_component_placement("U1", 100.0, 100.0, 180.0, 1)
        ep = [e for e in snap.net_to_endpoints["A"] if e.ref == "U1"][0]
        self.assertAlmostEqual(ep.x_mil, 60.0, places=9)
        self.assertAlmostEqual(ep.y_mil, 100.0, places=9)


class TestE10Gerber(unittest.TestCase):
    BASE = ("Gerber_TopLayer.GTL", "Gerber_BottomLayer.GBL", "Gerber_BoardOutlineLayer.GKO", "Gerber_TopSolderMaskLayer.GTS")

    def _zip(self, extra):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        z = os.path.join(d, "g.zip")
        with zipfile.ZipFile(z, "w") as f:
            for n, body in extra.items():
                f.writestr(n, body)
        return z

    def test_zip_with_no_drill_file(self):
        errs, _ = RL.check_gerber(self._zip({n: "G04*" for n in self.BASE}))
        self.assertEqual(errs, ["Gerber zip has no drill file"])
        errs, _ = RL.check_gerber(self._zip({**{n: "G04*" for n in self.BASE}, "readme.txt": "fab notes"}))
        self.assertEqual(errs, ["Gerber zip has no drill file"])

    def test_excellon_txt_is_a_drill_file(self):
        errs, _ = RL.check_gerber(self._zip({**{n: "G04*" for n in self.BASE}, "Board-RoundHoles.TXT": "M48\nINCH\n%\nT01C0.0118\n"}))
        self.assertEqual(errs, [])

    def test_paste_mask_is_not_solder_mask(self):
        files = {n: "G04*" for n in self.BASE if "SolderMask" not in n}
        files.update({"Gerber_TopPasteMaskLayer.GTP": "G04*", "Drill_PTH.DRL": "M48"})
        errs, _ = RL.check_gerber(self._zip(files))
        self.assertEqual(errs, ["Gerber zip has no solder mask file"])
        files["board-F_Mask.gbr"] = "G04*"
        self.assertEqual(RL.check_gerber(self._zip(files))[0], [])


if __name__ == "__main__":
    unittest.main()
