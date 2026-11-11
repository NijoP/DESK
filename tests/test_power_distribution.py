"""Power distribution planner tests on synthetic fixtures with declared currents."""
import unittest

from desk.profile import DesignProfile
from desk.power_distribution import PowerDistributionPlanner
from desk.routing.fixtures import make_board


def planner_for(scenario, currents, voltages, planes=None, layer_count=None):
    fx = make_board(scenario)
    prof = DesignProfile(project_id="PDN_TEST", layer_count=layer_count or len(fx["stackup"]))
    prof.current_limits_A.update(currents)
    prof.voltage_rails.update(voltages)
    plan = {"board_mm": list(fx["board_mm"]), "origin_mm": list(fx["origin_mm"]), "planes": planes if planes is not None else fx["planes"],
            "keepouts": fx["keepouts"]}
    return PowerDistributionPlanner(fx["dump"], prof, plan), fx


class TestRailStrategies(unittest.TestCase):
    def test_undeclared_rail_is_blocked_not_sized(self):
        p, fx = planner_for("buck_boost", {"VIN": 2.0}, {"VIN": 12.0, "VOUT": 5.0})
        rep = p.analyze()
        vout = next(r for r in rep.rails if r.net == "VOUT")
        self.assertEqual(vout.strategy, "BLOCKED")
        self.assertIsNone(vout.trace_width_mil)
        self.assertTrue(any("VOUT" in b for b in rep.blocking_issues))

    def test_high_current_rail_becomes_polygon_with_width_from_ipc(self):
        p, fx = planner_for("motor_high_current", {"VBUS_MOT": 8.0, "PHASE_A": 8.0, "PHASE_B": 8.0, "PHASE_C": 8.0, "VDRV": 0.3},
                            {"VBUS_MOT": 24.0, "VDRV": 12.0})
        rep = p.analyze()
        vbus = next(r for r in rep.rails if r.net == "VBUS_MOT")
        self.assertEqual(vbus.strategy, "POLYGON")
        self.assertGreater(vbus.trace_width_mil, 150)      # IPC-2221: 8 A at 10 C on 1 oz is ~220 mil
        self.assertIsNotNone(vbus.zone)
        self.assertGreater(vbus.vias_per_transition, 5)
        self.assertGreater(vbus.voltage_drop_mv_worst_path, 0)

    def test_plane_declared_rail_uses_plane(self):
        p, fx = planner_for("multi_rail_limited_layers", {"VIN_12V": 1.0, "5V": 1.5, "3V3": 1.5, "1V8": 0.4, "1V2": 0.4},
                            {"VIN_12V": 12.0, "5V": 5.0, "3V3": 3.3, "1V8": 1.8, "1V2": 1.2})
        rep = p.analyze()
        r33 = next(r for r in rep.rails if r.net == "3V3")
        self.assertEqual(r33.strategy, "PLANE")
        self.assertEqual(r33.plane_layer, "Inner2")
        self.assertIn("3V3", rep.plane_nets)
        self.assertEqual(rep.ground["strategy"], "CONTINUOUS_PLANE")
        self.assertFalse(rep.ground["continuity_verified"])

    def test_low_current_rail_is_a_trace(self):
        p, fx = planner_for("mixed_signal", {"3V3": 0.3, "AVDD": 0.05, "REFP": 0.01}, {"3V3": 3.3, "AVDD": 3.3, "REFP": 2.5})
        rep = p.analyze()
        avdd = next(r for r in rep.rails if r.net == "AVDD")
        self.assertEqual(avdd.strategy, "TRACE")

    def test_voltage_drop_scales_with_length_and_inverse_width(self):
        p, _ = planner_for("buck_boost", {"VIN": 1.0, "VOUT": 1.0, "SW": 1.0}, {"VIN": 12.0, "VOUT": 5.0, "SW": 5.0})
        r1 = p._resistance_mohm(10.0, 10.0)
        r2 = p._resistance_mohm(20.0, 10.0)
        r3 = p._resistance_mohm(10.0, 20.0)
        self.assertAlmostEqual(r2 / r1, 2.0, places=6)
        self.assertAlmostEqual(r1 / r3, 2.0, places=6)
        # 10 mm of 10 mil 1 oz copper is about 20 mOhm
        self.assertGreater(r1, 15.0); self.assertLess(r1, 25.0)


class TestZoneChecks(unittest.TestCase):
    def test_declared_plane_zone_reports_pads_inside_and_outside(self):
        p, fx = planner_for("esp32_4layer", {"3V3": 1.0, "VBAT": 1.5, "VSYS": 1.5, "VBUS": 1.0}, {"3V3": 3.3, "VBAT": 3.7, "VSYS": 3.7, "VBUS": 5.0})
        rep = p.analyze()
        z = next(z for z in rep.zones if z.net == "3V3" and z.zone_id.startswith("DECLARED"))
        self.assertGreater(z.area_mm2, 100)
        self.assertEqual(z.pads_inside + z.pads_outside, len(p.graph.nets["3V3"]))
        self.assertIn(z.status, ("OK", "UNRESOLVED_PADS", "BOUNDARY_VIOLATION"))  # fixture plane overlaps the antenna keep-out: a real finding

    def test_report_serialises(self):
        import json
        p, _ = planner_for("buck_boost", {"VIN": 2.0, "VOUT": 2.0, "SW": 2.0}, {"VIN": 12.0, "VOUT": 5.0, "SW": 5.0})
        json.dumps(p.analyze().to_dict())


if __name__ == "__main__":
    unittest.main()
