"""Reference-value tests for desk.ipc (trace ampacity, clearance, creepage, via current)."""
import math
import unittest

from desk import ipc


class TestTraceAmpacity(unittest.TestCase):
    def test_reference_widths(self):
        self.assertAlmostEqual(ipc.trace_width_mil(1.0), 11.9, delta=0.3)
        self.assertAlmostEqual(ipc.trace_width_mil(3.0), 54.1, delta=1.0)
        self.assertAlmostEqual(ipc.trace_width_mil(10.0), 284.9, delta=4.0)
        self.assertAlmostEqual(ipc.trace_width_mil(1.0, is_inner=True), 30.9, delta=0.7)

    def test_two_ounce_copper_halves_width(self):
        w1 = ipc.trace_width_mil(2.0, copper_oz=1.0)
        w2 = ipc.trace_width_mil(2.0, copper_oz=2.0)
        self.assertAlmostEqual(w1 / w2, 2.0, places=6)

    def test_inverse_round_trip(self):
        for i in (0.5, 1.0, 2.5, 6.0):
            w = ipc.trace_width_mil(i)
            self.assertAlmostEqual(ipc.trace_current_a(w), i, delta=0.02)

    def test_unknown_current_is_an_error_not_a_width(self):
        with self.assertRaises(ValueError):
            ipc.trace_width_mil(0.0)
        with self.assertRaises(ValueError):
            ipc.trace_width_mil(-1.0)


class TestClearance(unittest.TestCase):
    def test_table_rows_b2_external_uncoated(self):
        self.assertEqual(ipc.clearance_mm(5, "B2"), 0.10)
        self.assertEqual(ipc.clearance_mm(48, "B2"), 0.60)
        self.assertEqual(ipc.clearance_mm(230, "B2"), 1.25)
        self.assertEqual(ipc.clearance_mm(300, "B2"), 1.25)
        self.assertEqual(ipc.clearance_mm(400, "B2"), 2.50)

    def test_above_500v_formula(self):
        self.assertAlmostEqual(ipc.clearance_mm(600, "B2"), 2.5 + 0.005 * 100, places=6)
        self.assertAlmostEqual(ipc.clearance_mm(1000, "B1"), 0.25 + 0.0025 * 500, places=6)

    def test_internal_vs_external_vs_coated(self):
        self.assertEqual(ipc.clearance_mm(300, "B1"), 0.20)
        self.assertEqual(ipc.clearance_mm(300, "B4"), 0.80)
        self.assertEqual(ipc.clearance_mm(300, "B3"), 12.5)
        self.assertLess(ipc.clearance_mm(300, "B1"), ipc.clearance_mm(300, "B4"))
        self.assertLess(ipc.clearance_mm(300, "B2"), ipc.clearance_mm(300, "B3"))

    def test_mil_conversion(self):
        self.assertAlmostEqual(ipc.clearance_mil(400, "B2"), 2.5 * 39.37007874, places=2)

    def test_unknown_condition_rejected(self):
        with self.assertRaises(ValueError):
            ipc.clearance_mm(100, "Z9")


class TestCreepage(unittest.TestCase):
    def test_pd2_group_iii_mains(self):
        self.assertEqual(ipc.creepage_mm(250, 2, "IIIb"), 2.5)
        self.assertEqual(ipc.creepage_mm(230, 2, "IIIa"), 2.5)  # rounds up to the 250 V row
        self.assertEqual(ipc.creepage_mm(320, 2, "III"), 3.2)

    def test_material_group_ordering(self):
        self.assertLess(ipc.creepage_mm(250, 2, "I"), ipc.creepage_mm(250, 2, "II"))
        self.assertLess(ipc.creepage_mm(250, 2, "II"), ipc.creepage_mm(250, 2, "III"))

    def test_pollution_degree_1_is_smaller(self):
        self.assertLess(ipc.creepage_mm(250, 1), ipc.creepage_mm(250, 2, "I"))

    def test_out_of_table(self):
        with self.assertRaises(ValueError):
            ipc.creepage_mm(1500)
        with self.assertRaises(ValueError):
            ipc.creepage_mm(100, pollution_degree=3)

    def test_required_spacing_takes_the_maximum(self):
        # 230 V mains, external uncoated, PD2 group III: creepage 2.5 mm dominates clearance 1.25 mm.
        s = ipc.required_spacing_mil(230, "B2", 2, "III", manufacturer_min_mil=4.0)
        self.assertAlmostEqual(s, 2.5 * 39.37007874, places=1)
        # 3.3 V logic: fab minimum dominates.
        self.assertEqual(ipc.required_spacing_mil(3.3, "B2", 2, "III", manufacturer_min_mil=4.02), 4.02)


class TestVias(unittest.TestCase):
    def test_single_via_reference(self):
        # 12 mil drill, 1 mil plating: wall area = pi*13*1 = 40.84 mil^2 -> ~1.0 A at 10 C (IPC-2221 internal k)
        area = math.pi * 13.0
        expected = 0.024 * (10 ** 0.44) * (area ** 0.725)
        self.assertAlmostEqual(ipc.via_current_a(12.0, 1.0), expected, delta=0.01)
        self.assertGreater(expected, 0.9)
        self.assertLess(expected, 1.3)

    def test_vias_required_scales_with_current(self):
        per_via = ipc.via_current_a(12.0) * 0.8
        self.assertEqual(ipc.vias_required(1.0, 12.0), math.ceil(1.0 / per_via))
        self.assertEqual(ipc.vias_required(5.0, 12.0), math.ceil(5.0 / per_via))
        self.assertGreater(ipc.vias_required(5.0, 12.0), ipc.vias_required(1.0, 12.0))
        self.assertEqual(ipc.vias_required(0.1, 12.0), 1)

    def test_bad_inputs(self):
        with self.assertRaises(ValueError):
            ipc.via_current_a(0.0)
        with self.assertRaises(ValueError):
            ipc.vias_required(0.0, 12.0)


if __name__ == "__main__":
    unittest.main()
