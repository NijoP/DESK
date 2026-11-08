"""Tests for Hardened Engineering Design Profile and Electrical Assumptions."""

import unittest
from desk.profile import (
    DesignProfile,
    LayerStackup,
    ManufacturerProfile,
    CurrentConfidence,
)


class TestProfileHardening(unittest.TestCase):
    def setUp(self):
        self.profile = DesignProfile(
            project_id="HARDENED_TEST",
            layer_count=4,
            current_limits_A={"VIN": 3.5, "VBUS": 2.0},
        )

    def test_current_confidence_classification(self):
        # 1. Explicit verified limit
        curr_vin, conf_vin = self.profile.get_net_current_status("VIN")
        self.assertEqual(curr_vin, 3.5)
        self.assertEqual(conf_vin, CurrentConfidence.VERIFIED)

        # 2. Known power net but omitted from current_limits_A -> UNKNOWN
        curr_vbat, conf_vbat = self.profile.get_net_current_status("VBAT")
        self.assertEqual(conf_vbat, CurrentConfidence.UNKNOWN)

        # 3. Standard signal net -> ESTIMATED 0.2A
        curr_sig, conf_sig = self.profile.get_net_current_status("GPIO_1")
        self.assertEqual(curr_sig, 0.2)
        self.assertEqual(conf_sig, CurrentConfidence.ESTIMATED)

    def test_strict_current_mode_blocks_unknown_power_rails(self):
        # In strict mode, unknown high-current net must fail closed
        with self.assertRaises(ValueError) as ctx:
            self.profile.get_current_for_net("VBAT", allow_unknown_default=False)
        self.assertIn("UNKNOWN current capacity", str(ctx.exception))

        # With default allowed, it provides conservative 1.0A
        safe_curr = self.profile.get_current_for_net("VBAT", allow_unknown_default=True)
        self.assertEqual(safe_curr, 1.0)

    def test_stackup_physical_properties(self):
        stackup = self.profile.stackup
        self.assertEqual(len(stackup), 4)
        top = stackup[0]
        self.assertEqual(top.name, "Top")
        self.assertEqual(top.layer_type, "signal")
        self.assertEqual(top.dielectric_thickness_mil, 6.0)
        self.assertEqual(top.reference_layer_idx, 2)

    def test_manufacturer_presets(self):
        mfg_4l = ManufacturerProfile.get_preset("jlcpcb_standard_4layer")
        self.assertEqual(mfg_4l.min_trace_width_mil, 3.5)
        self.assertEqual(mfg_4l.min_clearance_mil, 3.5)
        self.assertEqual(mfg_4l.min_drill_mil, 8.0)
        self.assertTrue(mfg_4l.impedance_control_available)

    def test_profile_hash_invalidation(self):
        initial_hash = self.profile.compute_hash()
        
        # Modify an electrical parameter
        self.profile.current_limits_A["VIN"] = 5.0
        new_hash = self.profile.compute_hash()
        self.assertNotEqual(initial_hash, new_hash)

        # Invalidation domains
        invalidated = self.profile.affected_domains({"current_limits_A"})
        self.assertIn("M3", invalidated)
        self.assertIn("M4", invalidated)
        self.assertIn("M6", invalidated)


if __name__ == "__main__":
    unittest.main()
