"""Unit tests for Engineering Design Profile and Mental-Model Registry (Phase 2).
"""
import unittest
import os
import json
import tempfile
from desk.profile import DesignProfile, LayerStackup, NetClassProfile, DiffPairProfile, RFProfile
from desk.mental.registry import MentalModelRegistry
from desk.mental.models import MentalModel, CompiledPolicy

class TestDesignProfileAndMentalModels(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.profile = DesignProfile(
            project_id="TEST_PROJECT",
            version="1.0.0",
            board_dimensions_mm=(60.0, 40.0),
            layer_count=4,
            voltage_rails={"3V3": 3.3, "5V": 5.0, "VBUS": 5.0, "VBAT": 4.2},
            current_limits_A={"3V3": 0.8, "5V": 2.5, "VBUS": 2.0},
            critical_nets=["USB_DP", "USB_DN", "RF_ANT"]
        )

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_01_default_stackup_and_hash(self):
        self.assertEqual(len(self.profile.stackup), 4)
        layers = self.profile.get_stackup_layers()
        self.assertEqual(layers, ["Top", "Inner1_GND", "Inner2_PWR", "Bottom"])
        h = self.profile.compute_hash()
        self.assertTrue(len(h) >= 12)
        self.assertEqual(h, self.profile.profile_hash)

    def test_02_serialization_roundtrip(self):
        p_path = os.path.join(self.tmp_dir.name, "profile.json")
        self.profile.save(p_path)
        self.assertTrue(os.path.exists(p_path))

        loaded = DesignProfile.load(p_path)
        self.assertEqual(loaded.project_id, "TEST_PROJECT")
        self.assertEqual(loaded.board_dimensions_mm, (60.0, 40.0))
        self.assertEqual(loaded.layer_count, 4)
        self.assertEqual(loaded.current_limits_A["5V"], 2.5)
        self.assertEqual(loaded.compute_hash(), self.profile.compute_hash())

    def test_03_profile_driven_trace_width(self):
        # 5V rail has 2.5A current limit -> should require substantial trace width (> 20 mil)
        w_5v = self.profile.derive_trace_width_mil("5V", is_inner=False)
        self.assertGreater(w_5v, 20.0)

        # 3V3 rail has 0.8A limit
        w_3v3 = self.profile.derive_trace_width_mil("3V3", is_inner=False)
        self.assertLess(w_3v3, w_5v)
        self.assertGreater(w_3v3, 5.0)

        # Signal net with no specific current -> default min width
        w_sig = self.profile.derive_trace_width_mil("GPIO_LED", is_inner=False)
        self.assertEqual(w_sig, self.profile.manufacturing.min_trace_width_mil)

    def test_04_fine_grained_affected_domains(self):
        # Changing only voltage rails should only invalidate M1 (Schematic) and M6 (Verification)
        aff = self.profile.affected_domains({"voltage_rails"})
        self.assertIn("M1", aff)
        self.assertIn("M6", aff)
        self.assertNotIn("M2", aff)  # Placement unaffected

        # Changing RF lines affects M3, M4, M6
        aff_rf = self.profile.affected_domains({"rf_lines"})
        self.assertIn("M3", aff_rf)
        self.assertIn("M4", aff_rf)
        self.assertNotIn("M1", aff_rf)

    def test_05_mental_model_registry(self):
        models = MentalModelRegistry.list_models()
        self.assertEqual(len(models), 6)
        expected = ["M1_SCHEMATIC", "M2_PLACEMENT", "M3_ROUTING", "M4_COPPER_GROUND", "M5_ELECTRICAL_MFG", "M6_VERIFICATION_REVIEW"]
        self.assertEqual(models, sorted(expected))

        m1 = MentalModelRegistry.get("M1_SCHEMATIC")
        self.assertIsNotNone(m1)
        self.assertEqual(m1.domain, "schematic")
        self.assertTrue(m1.hard_constraints["every_pin_accounted"])

        m6 = MentalModelRegistry.get("M6_VERIFICATION_REVIEW")
        self.assertIsNotNone(m6)
        self.assertTrue(m6.hard_constraints["zero_unintended_shorts"])

if __name__ == "__main__":
    unittest.main()
