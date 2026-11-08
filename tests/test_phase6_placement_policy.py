"""Unit tests for Phase 6: Connecting compiled policies to placement engines.
"""
import unittest
from desk.profile import DesignProfile, ManufacturerProfile, ThermalProfile
from desk.placement_intel import PlacementIntelligenceEngine, ComponentRequirement
from desk import placement

class TestPhase6PlacementPolicy(unittest.TestCase):

    def setUp(self):
        self.profile = DesignProfile(
            project_id="P6_TEST",
            board_dimensions_mm=(70.0, 45.0),
            manufacturing=ManufacturerProfile(
                name="custom_mfg",
                min_clearance_mil=6.0,  # 6 mil ~= 0.1524 mm
                copper_to_edge_mil=20.0 # 20 mil ~= 0.508 mm
            ),
            thermal=ThermalProfile(
                max_temperature_rise_c=5.0 # tight thermal constraint -> triggers increased heat spacing
            )
        )

    def test_01_placement_engine_profile_dimensions(self):
        engine = PlacementIntelligenceEngine(board_dims_mm=(50.0, 50.0), profile=self.profile)
        # Must adopt profile's 70 x 45 mm instead of fallback 50 x 50
        self.assertEqual(engine.W, 70.0)
        self.assertEqual(engine.H, 45.0)

    def test_02_placement_check_profile_overrides(self):
        dump = {
            "C1": {
                "x": 393.7, "y": 393.7, "rot": 0, "layer": 1, "fp": "C0402",
                "pads": [{"num": "1", "dx": 0, "dy": 0, "shape": ["RECT", 15, 15], "net": "GND", "layer": 1}]
            }
        }
        plan = {"board_mm": [70.0, 45.0], "parts": [["C1", 10.0, 10.0, 0, "T", "test"]]}

        # Run placement check with profile
        E, W, M = placement.check(dump, plan, profile=self.profile)
        self.assertIsInstance(E, list)
        self.assertIsInstance(W, list)

if __name__ == "__main__":
    unittest.main()
