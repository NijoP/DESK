"""Adversarial Computational Geometry Tests for Copper Zones and Keepouts."""

import unittest
from desk.copper import (
    CopperPlaneEngine,
    CopperZoneSpec,
    segments_intersect,
    ReturnPathDiscontinuity,
)
from desk.profile import LayerStackup


class TestCopperGeometry(unittest.TestCase):
    def test_segment_intersection(self):
        # 1. Standard crossing lines
        self.assertTrue(segments_intersect((0, 0), (10, 10), (0, 10), (10, 0)))
        
        # 2. Parallel non-intersecting lines
        self.assertFalse(segments_intersect((0, 0), (10, 0), (0, 5), (10, 5)))
        
        # 3. Collinear overlapping lines
        self.assertTrue(segments_intersect((0, 0), (5, 0), (3, 0), (8, 0)))
        
        # 4. T-junction intersection
        self.assertTrue(segments_intersect((0, 0), (10, 0), (5, 0), (5, 5)))

    def test_engulfed_keepout_detection(self):
        """A keepout placed completely inside a large polygon must be detected as a collision."""
        zone = CopperZoneSpec(
            zone_id="ZONE_GND",
            net="GND",
            layer=1,
            layer_name="Top",
            # Large zone spanning (10, 10) to (50, 50)
            points_mm=[(10.0, 10.0), (50.0, 10.0), (50.0, 50.0), (10.0, 50.0)],
        )
        # Keepout located strictly in the center at (20, 20) to (30, 30)
        # Note: None of the zone's vertices are inside this keepout!
        keepouts = [
            {"name": "ANTENNA_KEEPOUT", "rect_mm": (20.0, 20.0, 30.0, 30.0), "layer": 1}
        ]
        violations = CopperPlaneEngine.check_polygon_boundary(
            zone, board_dims_mm=(60.0, 60.0), edge_setback_mm=0.5, keepouts=keepouts
        )
        self.assertTrue(len(violations) > 0)
        self.assertTrue(any("engulfs keepout 'ANTENNA_KEEPOUT'" in v for v in violations))

    def test_polygon_edge_crossing_keepout_detection(self):
        """A polygon edge that intersects a keepout boundary must be detected."""
        zone = CopperZoneSpec(
            zone_id="ZONE_PWR",
            net="VCC",
            layer=1,
            layer_name="Top",
            # Edge from (5, 25) to (35, 25) crosses keepout (20, 20, 30, 30)
            points_mm=[(5.0, 10.0), (35.0, 10.0), (35.0, 25.0), (5.0, 25.0)],
        )
        keepouts = [
            {"name": "ISOLATION_SLOT", "rect_mm": (20.0, 20.0, 30.0, 30.0), "layer": 1}
        ]
        violations = CopperPlaneEngine.check_polygon_boundary(
            zone, board_dims_mm=(60.0, 60.0), edge_setback_mm=0.5, keepouts=keepouts
        )
        self.assertTrue(len(violations) > 0)
        self.assertTrue(any("ISOLATION_SLOT" in v for v in violations))

    def test_concave_ground_plane_return_path_continuity(self):
        """For an L-shaped concave ground plane, tracks crossing the void must be caught as slot_crossing."""
        # L-shaped ground plane: spans (0,0) to (20,40) and (20,0) to (40,20), cutout at (20,20) to (40,40)
        l_shape = [
            (0.0, 0.0), (40.0, 0.0), (40.0, 20.0), (20.0, 20.0), (20.0, 40.0), (0.0, 40.0)
        ]
        plane = CopperZoneSpec(
            zone_id="GND_L2",
            net="GND",
            layer=2,
            layer_name="Bottom",
            points_mm=l_shape,
            is_ground_plane=True,
        )
        stackup = [
            LayerStackup(1, "Top", "signal"),
            LayerStackup(2, "Bottom", "plane"),
        ]
        # Track running in the void cutout region: from (25, 25) to (35, 35) on Layer 1
        # Bounding box of the plane is (0,0) to (40,40), so naive bounding box would falsely say PASS!
        track = {
            "net": "SPI_CLK",
            "layer": 1,
            "start_mm": (25.0, 25.0),
            "end_mm": (35.0, 35.0),
        }
        discon = CopperPlaneEngine.evaluate_return_path_continuity([track], [plane], stackup)
        self.assertEqual(len(discon), 1)
        self.assertEqual(discon[0].discontinuity_type, "slot_crossing")
        self.assertEqual(discon[0].net, "SPI_CLK")


if __name__ == "__main__":
    unittest.main()
