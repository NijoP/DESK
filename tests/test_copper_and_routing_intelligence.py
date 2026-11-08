"""Unit tests for Phase 7: Copper and Ground Plane Intelligence and Routing Profiles.
"""
import unittest
from desk.profile import DesignProfile, LayerStackup, DiffPairProfile
from desk.copper import CopperPlaneEngine, CopperZoneSpec, StitchingViaArray
from desk.router import StackupManager, TraceWidthCalculator, RoutingPlanGenerator
from desk.models import NetConnectivityGraph, NetEndpoint

class TestCopperAndRoutingIntelligence(unittest.TestCase):

    def setUp(self):
        # 4-layer custom RF/power profile: Top=Signal, L2=GND, L3=GND/Inner, L4=PWR/Bottom
        custom_stackup = [
            LayerStackup(1, "Top_RF", "signal", copper_thickness_oz=1.0),
            LayerStackup(2, "Inner1_GND", "plane", copper_thickness_oz=1.0),
            LayerStackup(3, "Inner2_GND", "plane", copper_thickness_oz=1.0),
            LayerStackup(4, "Bottom_PWR", "signal", copper_thickness_oz=2.0),
        ]
        self.profile = DesignProfile(
            project_id="RF_POWER_BOARD",
            board_dimensions_mm=(80.0, 50.0),
            layer_count=4,
            stackup=custom_stackup,
            current_limits_A={"VBAT": 4.0, "3V3": 0.5},
            diff_pairs={"USB": DiffPairProfile("USB", "USB_DP", "USB_DN", 90.0)}
        )

    def test_01_stackup_manager_adopts_profile(self):
        # Verify stackup manager directly uses the profile's custom layer names
        layers = StackupManager.detect_stackup({}, profile=self.profile)
        self.assertEqual(layers, ["Top_RF", "Inner1_GND", "Inner2_GND", "Bottom_PWR"])

    def test_02_trace_width_calculator_uses_profile(self):
        # 4A VBAT on 2 oz copper
        w_vbat = TraceWidthCalculator.get_width_mil("VBAT", profile=self.profile)
        self.assertGreater(w_vbat, 15.0)

    def test_03_ground_plane_generation(self):
        zones = CopperPlaneEngine.generate_ground_planes((80.0, 50.0), self.profile)
        # Should generate ground planes on Inner1_GND and Inner2_GND
        self.assertEqual(len(zones), 2)
        self.assertEqual(zones[0].net, "GND")
        self.assertTrue(zones[0].is_ground_plane)
        # Verify edge setback is respected
        x_min = min(p[0] for p in zones[0].points_mm)
        self.assertGreaterEqual(x_min, 0.2)

    def test_04_stitching_via_synthesis(self):
        # Obstacle at (20, 20) with 3mm radius
        obstacles = [(20.0, 20.0, 3.0)]
        vias = CopperPlaneEngine.synthesize_stitching_vias((50.0, 50.0), obstacles, grid_spacing_mm=5.0)
        self.assertGreater(len(vias.via_locations), 10)
        # Verify no via was placed within the obstacle zone
        for vx, vy in vias.via_locations:
            dist = ((vx - 20.0) ** 2 + (vy - 20.0) ** 2) ** 0.5
            self.assertGreaterEqual(dist, 3.5)

    def test_05_return_path_continuity_check(self):
        zones = CopperPlaneEngine.generate_ground_planes((80.0, 50.0), self.profile)
        # Critical track within board
        critical_tracks = [
            {"net": "RF_50R", "layer": 1, "start_mm": (10.0, 10.0), "end_mm": (30.0, 10.0)},
            # Track crossing beyond plane boundary (at x=0.1, outside plane setback)
            {"net": "USB_DP", "layer": 1, "start_mm": (0.05, 10.0), "end_mm": (20.0, 10.0)}
        ]
        discon = CopperPlaneEngine.evaluate_return_path_continuity(critical_tracks, zones, self.profile.stackup)
        # USB_DP should be flagged for slot crossing / boundary violation
        self.assertTrue(any(d.net == "USB_DP" for d in discon))

if __name__ == "__main__":
    unittest.main()
