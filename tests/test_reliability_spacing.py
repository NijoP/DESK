"""Spacing model (desk/spacing.py) and routing feasibility (desk/routing/feasibility.py).

UPS_1000 fixture: 58-70 V nets terminating on 1.27 mm-pitch packages (LM5164, UCC21520). The historical rule put
1.25-1.30 mm of creepage into the router clearance of those nets, above the 0.65 mm pad gap. The tests prove that
(1) the default policy is unchanged (nothing weakened silently), (2) creepage and clearance are separate quantities,
(3) a rule the geometry cannot meet becomes a BLOCKING engineering decision naming pad, net, rule and gap, and
(4) no code path lowers a spacing value on its own.
"""
import unittest

from desk import ipc
from desk import spacing as SP
from desk.profile import DesignProfile, ManufacturerProfile
from desk.routing import feasibility as FZ

MIL = 39.37007874


def ups_profile(policy="CREEPAGE_AS_CLEARANCE", barriers=None):
    return DesignProfile(project_id="UPS", voltage_rails={"VBUS": 58.4, "SW12": 60.0, "GND": 0.0, "3V3": 3.3, "VOUT_EXT": 70.4},
                         current_limits_A={"VBUS": 20.0, "SW12": 2.0, "VOUT_EXT": 20.0, "3V3": 1.0},
                         clearance_condition="B2", pollution_degree=2, material_group="IIIa",
                         manufacturing=ManufacturerProfile(min_clearance_mil=4.02), spacing_policy=policy,
                         insulation_barriers=barriers or [])


class LegacyEquivalence(unittest.TestCase):
    def test_default_policy_reproduces_the_historical_rule_exactly(self):
        p = ups_profile()
        for net in ("VBUS", "SW12", "3V3", "VOUT_EXT", "GND"):
            self.assertAlmostEqual(p.derive_clearance_mil(net, "GND"), p._legacy_derive_clearance_mil(net, "GND"), places=6, msg=net)
        self.assertAlmostEqual(p.derive_clearance_mil("VBUS", "GND"), 49.21, places=1)      # 1.25 mm creepage row (UPS DSN)
        self.assertAlmostEqual(p.derive_clearance_mil("VOUT_EXT", "GND"), 51.18, places=1)  # 1.30 mm

    def test_quantities_are_separate(self):
        req = ups_profile().spacing_requirement("VBUS", "GND")
        self.assertAlmostEqual(req.functional_clearance_mm, 0.60)       # IPC-2221B B2, 51-100 V
        self.assertIsNone(req.creepage_mm)                               # no declared barrier between VBUS and GND
        self.assertAlmostEqual(req.fabricator_min_mm, 4.02 / MIL, places=4)
        self.assertEqual(req.policy, SP.SpacingPolicy.CREEPAGE_AS_CLEARANCE)
        self.assertAlmostEqual(req.router_rule_mm, 1.25)                 # the legacy max() still applies under the default
        self.assertFalse(req.table_verified)                             # ipc.verified_against_standard is False
        self.assertAlmostEqual(ipc.creepage_mm(58.4, 2, "IIIa"), 1.25)


class FunctionalPolicy(unittest.TestCase):
    def test_functional_policy_uses_clearance_and_creepage_only_across_barriers(self):
        p = ups_profile("FUNCTIONAL")
        self.assertAlmostEqual(p.derive_clearance_mil("VBUS", "GND"), 0.60 * MIL, places=1)
        barrier = [{"name": "HV-SELV", "nets_a": ["VBUS"], "nets_b": ["3V3"], "working_voltage_v": 60.0, "insulation": "basic",
                    "pollution_degree": 2, "material_group": "IIIa"}]
        p2 = ups_profile("FUNCTIONAL", barrier)
        self.assertAlmostEqual(p2.spacing_requirement("VBUS", "3V3").creepage_mm, 1.25)
        self.assertAlmostEqual(p2.derive_clearance_mil("VBUS", "3V3"), 1.25 * MIL, places=1)   # across the barrier: creepage
        self.assertAlmostEqual(p2.derive_clearance_mil("VBUS", "GND"), 0.60 * MIL, places=1)   # inside the circuit: clearance
        reinforced = [{**barrier[0], "insulation": "reinforced"}]
        self.assertAlmostEqual(ups_profile("FUNCTIONAL", reinforced).spacing_requirement("VBUS", "3V3").creepage_mm, 2.50)

    def test_policy_round_trips_through_json_and_unknown_values_fall_back(self):
        d = ups_profile("FUNCTIONAL").to_dict()
        self.assertEqual(d["spacing_policy"], "FUNCTIONAL")
        self.assertEqual(DesignProfile.from_dict(d).spacing_policy, "FUNCTIONAL")
        self.assertEqual(SP.parse_policy("whatever"), SP.SpacingPolicy.CREEPAGE_AS_CLEARANCE)

    def test_unknown_high_voltage_net_still_fails_closed(self):
        with self.assertRaises(ValueError):
            ups_profile("FUNCTIONAL").derive_clearance_mil("HV_BUS", "GND")


def soic_board(rule_net="SW12", pitch_mil=50.0, pad_w_mil=24.0, pad_h_mil=70.0):
    """U1: an 8-pin 1.27 mm-pitch package; pins 1-4 on nets SW12, GND, FB, 3V3; a 0603 R1 far away."""
    nets = [rule_net, "GND", "FB", "3V3"]
    pads = [{"num": str(i + 1), "net": nets[i], "dx": i * pitch_mil, "dy": 0.0, "w": pad_w_mil, "h": pad_h_mil, "layer": 1} for i in range(4)]
    return {"U1": {"x": 1000.0, "y": 1000.0, "layer": 1, "rot": 0, "pads": pads},
            "R1": {"x": 3000.0, "y": 1000.0, "layer": 1, "rot": 0, "pads": [{"num": "1", "net": rule_net, "dx": -30.0, "dy": 0, "w": 35, "h": 40, "layer": 1},
                                                                           {"num": "2", "net": "GND", "dx": 30.0, "dy": 0, "w": 35, "h": 40, "layer": 1}]}}


class Feasibility(unittest.TestCase):
    def test_creepage_rule_on_a_fine_pitch_pin_is_blocked_by_clearance_with_a_decision(self):
        rep = FZ.evaluate(soic_board(), {"SW12": 49.21}, fab_min_mil=4.02, stackup=["Top", "Bottom"])
        self.assertFalse(rep.feasible)
        blocked = [b for b in rep.blocked if b.classification == "BLOCKED_BY_CLEARANCE"]
        self.assertEqual(sorted(b.pad_id for b in blocked), ["R1.1", "U1.1"])   # the 0603 on the same net is blocked too
        b = [x for x in blocked if x.pad_id == "U1.1"][0]
        self.assertEqual((b.net, b.neighbour, b.neighbour_net), ("SW12", "U1.2", "GND"))
        self.assertAlmostEqual(b.gap_mil, 26.0)                           # 50 mil pitch - 24 mil pad width
        self.assertAlmostEqual(b.rule_mil, 49.21)
        self.assertIn("0.660 mm", b.detail)
        self.assertEqual(len(rep.decisions), 1)
        d = rep.decisions[0]
        self.assertEqual((d.status, d.net, sorted(d.pads)), ("BLOCKING", "SW12", ["R1.1", "U1.1"]))
        self.assertAlmostEqual(d.rule_mm, 49.21 / MIL, places=3)
        self.assertAlmostEqual(d.pin_field_mm, 25.0 / MIL, places=3)          # the smallest gap on the net (R1: 60 - 35)
        self.assertTrue(any("FUNCTIONAL" in o for o in d.options))
        self.assertIn("No spacing value was changed", d.note)
        self.assertEqual(rep.classes["BLOCKED_BY_CLEARANCE"], 2)

    def test_ipc_clearance_fits_the_same_pin_field(self):
        rep = FZ.evaluate(soic_board(), {"SW12": 23.62}, fab_min_mil=4.02)    # 0.60 mm IPC-2221B B2
        self.assertTrue(rep.feasible)
        self.assertEqual(rep.decisions, [])
        self.assertEqual(rep.classes["LEGAL_AND_ROUTABLE"], 6)

    def test_rule_never_lowered_by_evaluation(self):
        rules = {"SW12": 49.21}
        FZ.evaluate(soic_board(), rules, fab_min_mil=4.02)
        self.assertEqual(rules, {"SW12": 49.21})

    def test_package_geometry_below_fab_minimum(self):
        rep = FZ.evaluate(soic_board(pitch_mil=26.0), {}, fab_min_mil=4.02)   # 2 mil gap
        self.assertEqual(rep.classes["BLOCKED_BY_PACKAGE_GEOMETRY"], 4)
        self.assertFalse(rep.feasible)

    def test_neighbouring_component_is_a_placement_change_not_a_block(self):
        board = soic_board()
        board["R1"]["x"] = 1000.0 + 150.0 + 30.0 + 12.0 + 5.0                  # R1.1 lands 5 mil right of U1.4
        board["R1"]["pads"][0]["net"] = "VBUS"
        rep = FZ.evaluate(board, {"VBUS": 49.21}, fab_min_mil=4.02)
        kinds = {b.pad_id: b.classification for b in rep.blocked}
        self.assertEqual(kinds.get("R1.1"), "ROUTABLE_WITH_PLACEMENT_CHANGE")
        self.assertTrue(rep.feasible)                                        # placement changes do not block the engine

    def test_keepout_and_stackup(self):
        rep = FZ.evaluate(soic_board(), {}, fab_min_mil=4.02, route_keepouts=[{"name": "hole", "rect_mm": [20, 20, 30, 30], "side": "both"}])
        self.assertEqual(rep.classes["BLOCKED_BY_KEEP_OUT"], 4)
        rep2 = FZ.evaluate(soic_board(), {}, fab_min_mil=4.02, stackup=["Top", "Inner1", "Inner2", "Bottom"], plane_layers={2: "GND", 3: "GND"})
        self.assertEqual(rep2.routable_layers, [1, 4])
        self.assertTrue(any("only 2 routable" in w for w in rep2.warnings))
        rep3 = FZ.evaluate(soic_board(), {}, fab_min_mil=4.02, stackup=["Top", "Bottom"], plane_layers={1: "GND"})
        self.assertEqual(rep3.classes["BLOCKED_BY_STACKUP"], 6)

    def test_rect_gap_is_axis_aware(self):
        a = FZ._Pad("a", "U", "1", "N1", 0, 0, 24, 70, "T")
        b = FZ._Pad("b", "U", "2", "N2", 50, 0, 24, 70, "T")
        self.assertAlmostEqual(FZ.rect_gap_mil(a, b), 26.0)                 # not 50 - 70 (the circle model said overlap)
        c = FZ._Pad("c", "U", "3", "N3", 0, 100, 24, 70, "T")
        self.assertAlmostEqual(FZ.rect_gap_mil(a, c), 30.0)

    def test_report_serialises(self):
        d = FZ.evaluate(soic_board(), {"SW12": 49.21}, fab_min_mil=4.02).to_dict()
        self.assertIn("decisions", d)
        self.assertEqual(d["blocked"][0]["pad_id"], "U1.1")
        self.assertLess(d["analysis_ms"], 50.0)


if __name__ == "__main__":
    unittest.main()
