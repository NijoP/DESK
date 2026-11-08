"""Unit tests for Mental-Model Compiler and Context Integration (Phase 3).
"""
import unittest
import os
import json
import tempfile
from desk.profile import DesignProfile
from desk.mental.compiler import PolicyCompiler
from desk.mental.registry import MentalModelRegistry
from desk.context import Engine

class TestMentalCompiler(unittest.TestCase):

    def setUp(self):
        self.profile = DesignProfile(
            project_id="COMPILER_TEST",
            version="1.0.0",
            board_dimensions_mm=(55.0, 35.0),
            layer_count=2,
            voltage_rails={"3V3": 3.3, "5V": 5.0},
            current_limits_A={"5V": 2.0, "3V3": 0.5},
            critical_nets=["USB_DP", "USB_DN"]
        )

    def test_01_compile_m1_schematic(self):
        policy = PolicyCompiler.compile("M1_SCHEMATIC", "block_spec", self.profile, {"block_id": "02_PWR"})
        self.assertEqual(policy.model_id, "M1_SCHEMATIC")
        self.assertTrue(any("02_PWR" in r for r in policy.compact_rules))
        self.assertTrue(any("Rail 5V: 5.0V" in r for r in policy.compact_rules))
        self.assertLess(policy.token_estimate, 400)

    def test_02_compile_m2_placement(self):
        policy = PolicyCompiler.compile("M2_PLACEMENT", "component_placement", self.profile)
        self.assertEqual(policy.model_id, "M2_PLACEMENT")
        self.assertTrue(any("55.0 x 35.0 mm" in r for r in policy.compact_rules))
        self.assertTrue(policy.hard_constraints["zero_mating_envelope_intrusion"])
        self.assertIn("parts", policy.output_schema["required"])

    def test_03_compile_m3_routing(self):
        policy = PolicyCompiler.compile("M3_ROUTING", "net_routing", self.profile, {"nets": ["5V", "3V3"]})
        self.assertEqual(policy.model_id, "M3_ROUTING")
        self.assertTrue(any("Net 5V: min width" in r for r in policy.compact_rules))
        self.assertEqual(policy.hard_constraints["stackup_layers"], ["Top", "Bottom"])

    def test_04_cache_and_invalidation(self):
        key = PolicyCompiler.get_cache_key("M2_PLACEMENT", "general", self.profile, "1.0.0")
        p1 = PolicyCompiler.compile("M2_PLACEMENT", "general", self.profile)
        self.assertIn(key, PolicyCompiler._cache)

        # Invalidate placement domain
        PolicyCompiler.invalidate_on_profile_change(self.profile, {"board_dimensions_mm"})
        self.assertNotIn(key, PolicyCompiler._cache)

    def test_05_compact_prompt_rendering(self):
        policy = PolicyCompiler.compile("M4_COPPER_GROUND", "plane_generation", self.profile)
        prompt = policy.to_compact_prompt()
        self.assertIn("HARD CONSTRAINTS:", prompt)
        self.assertIn("TASK RULES:", prompt)
        self.assertIn("VERIFICATION CHECKLIST:", prompt)

if __name__ == "__main__":
    unittest.main()
