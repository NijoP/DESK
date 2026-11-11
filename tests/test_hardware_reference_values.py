"""Numeric reference tests for hardware models (roadmap QA-04).

Until now the suite only asserted monotonicity. These tests pin the implemented
formulas to values derived independently from the published IPC-2221 power law
so that a silent change to a constant is caught.

IPC-2221: I = k * dT^0.44 * A^0.725   (A in mil^2, k = 0.048 external, 0.024 internal)
=> A = (I / (k * dT^0.44)) ** (1 / 0.725);  width_mil = A / (1.37 mil/oz * oz)
"""
import unittest

from desk.routing.width import TraceWidthManager
from desk.profile import DesignProfile


def ipc2221_width_mil(current_a, inner=False, oz=1.0, d_t=10.0):
    k = 0.024 if inner else 0.048
    area = (current_a / (k * d_t ** 0.44)) ** (1 / 0.725)
    return area / (1.37 * oz)


class TestIPC2221Widths(unittest.TestCase):
    CASES = [
        # (current A, inner, oz, dT) -> independently derived width (mil)
        (1.0, False, 1.0, 10.0),
        (3.0, False, 1.0, 10.0),
        (10.0, False, 1.0, 10.0),
        (1.0, True, 1.0, 10.0),
        (2.0, False, 2.0, 20.0),
    ]

    def test_matches_power_law_within_two_percent(self):
        for i, inner, oz, dt in self.CASES:
            got = TraceWidthManager.calculate_ipc2152_width(i, is_inner=inner, copper_oz=oz, temp_rise_C=dt)
            exp = ipc2221_width_mil(i, inner, oz, dt)
            with self.subTest(current=i, inner=inner, oz=oz, dT=dt):
                # The implementation applies a 5 mil manufacturing floor; all cases here are above it.
                self.assertAlmostEqual(got, exp, delta=max(0.02 * exp, 0.05))

    def test_known_reference_points(self):
        # Values an engineer would check against an IPC-2221 calculator.
        self.assertAlmostEqual(TraceWidthManager.calculate_ipc2152_width(1.0), 11.9, delta=0.3)
        self.assertAlmostEqual(TraceWidthManager.calculate_ipc2152_width(3.0), 54.1, delta=1.0)
        self.assertAlmostEqual(TraceWidthManager.calculate_ipc2152_width(1.0, is_inner=True), 30.9, delta=0.7)

    def test_inner_layers_are_wider_than_outer_for_same_current(self):
        self.assertGreater(TraceWidthManager.calculate_ipc2152_width(1.0, is_inner=True),
                           TraceWidthManager.calculate_ipc2152_width(1.0, is_inner=False))

    def test_zero_current_does_not_return_a_physical_width(self):
        # Documents current behaviour: <=0 A returns a 6 mil placeholder. Roadmap H-02 will make
        # unknown current fail closed; when that lands this test should expect an error instead.
        self.assertEqual(TraceWidthManager.calculate_ipc2152_width(0.0), 6.0)


class TestClearanceTiers(unittest.TestCase):
    def setUp(self):
        self.p = DesignProfile(project_id="REFTEST")
        self.p.voltage_rails = {"VIN": 48.0, "HV": 300.0, "GND": 0.0, "3V3": 3.3}

    def test_low_voltage_uses_manufacturer_minimum(self):
        self.assertEqual(self.p.derive_clearance_mil("3V3", "GND"), self.p.manufacturing.min_clearance_mil)

    def test_mid_voltage_tier(self):
        # 48 V external uncoated: IPC-2221B B2 0.6 mm; IEC 60664-1 PD2 group III creepage at 50 V row 1.2 mm.
        self.assertAlmostEqual(self.p.derive_clearance_mil("VIN", "GND"), 1.2 * 39.37007874, places=1)

    def test_high_voltage_uses_standards_tables(self):
        # 300 V: clearance B2 1.25 mm, creepage PD2/III 3.2 mm -> 3.2 mm = 126 mil (was 24 mil before H-01).
        self.assertAlmostEqual(self.p.derive_clearance_mil("HV", "GND"), 3.2 * 39.37007874, places=1)

    def test_internal_layer_condition_is_smaller(self):
        self.p.clearance_condition = "B1"
        self.p.pollution_degree = 1
        self.assertAlmostEqual(self.p.derive_clearance_mil("HV", "GND"),
                               max(0.20, 0.75) * 39.37007874, places=1)

    def test_undeclared_high_voltage_net_fails_closed(self):
        with self.assertRaises(ValueError):
            self.p.derive_clearance_mil("MAINS_L", "GND")
        self.assertIn("MAINS_L", " ".join(self.p.validate_electrical_inputs(["MAINS_L", "3V3"])))

    def test_undeclared_power_rail_current_fails_closed(self):
        with self.assertRaises(ValueError):
            self.p.get_current_for_net("VBAT")
        self.p.unknown_current_policy = "default_1A"
        self.assertEqual(self.p.get_current_for_net("VBAT"), 1.0)


if __name__ == "__main__":
    unittest.main()
