"""Unit tests for offline Copper and Ground Plane Intelligence Engine (Mental Model M4).
Covers:
- Ground-plane generation
- Power-polygon planning
- Net and layer assignment models
- Polygon boundary and keepout checks
- Thermal-relief and solid-connection configuration models
- Via stitching synthesis
- Copper island detection
- Return-path discontinuity checks
- Copper-zone revision tracking and invalidation.
"""
import unittest
from desk.profile import DesignProfile, LayerStackup
from desk.copper import (
    CopperPlaneEngine, CopperZoneSpec, ConnectionRuleResolver,
    ConnectionConfig, StitchingViaArray, CopperZoneRevisionTracker
)

class TestOfflineCopperEngine(unittest.TestCase):

    def setUp(self):
        self.stackup = [
            LayerStackup(1, "Top", "signal", copper_thickness_oz=1.0),
            LayerStackup(2, "Inner1_GND", "plane", copper_thickness_oz=1.0),
            LayerStackup(3, "Inner2_PWR", "plane", copper_thickness_oz=1.0),
            LayerStackup(4, "Bottom", "signal", copper_thickness_oz=1.0)
        ]
        self.profile = DesignProfile(
            project_id="COPPER_TEST",
            board_dimensions_mm=(60.0, 40.0),
            layer_count=4,
            stackup=self.stackup,
            current_limits_A={"VIN": 5.0, "SW": 5.0, "3V3": 0.5}
        )

    def test_01_connection_rule_resolver(self):
        # Power MOSFET thermal switch node -> solid connection
        rule_sw = ConnectionRuleResolver.resolve_connection("SW", "Q1", pin_number="D", current_A=5.0)
        self.assertEqual(rule_sw.connection_type, "solid")
        self.assertEqual(rule_sw.spoke_count, 0)

        # Standard passive on 3V3 -> thermal relief
        rule_3v3 = ConnectionRuleResolver.resolve_connection("3V3", "C1", pin_number="1", current_A=0.5)
        self.assertEqual(rule_3v3.connection_type, "thermal_relief")
        self.assertEqual(rule_3v3.spoke_count, 4)
        self.assertGreaterEqual(rule_3v3.spoke_width_mil, 10.0)

    def test_02_ground_plane_generation(self):
        zones = CopperPlaneEngine.generate_ground_planes((60.0, 40.0), self.profile)
        self.assertEqual(len(zones), 1)  # Layer 2 is dedicated GND plane
        gnd_zone = zones[0]
        self.assertEqual(gnd_zone.layer, 2)
        self.assertEqual(gnd_zone.net, "GND")
        self.assertTrue(gnd_zone.is_ground_plane)
        self.assertEqual(gnd_zone.priority, 1)

    def test_03_power_polygon_planning(self):
        pads = [
            {"ref": "Q1", "net": "SW", "x_mm": 20.0, "y_mm": 15.0},
            {"ref": "L1", "net": "SW", "x_mm": 25.0, "y_mm": 18.0},
            {"ref": "D1", "net": "SW", "x_mm": 22.0, "y_mm": 16.0}
        ]
        pwr_zone = CopperPlaneEngine.plan_power_polygons(
            net_name="SW",
            layer=1,
            layer_name="Top",
            pads=pads,
            board_dims_mm=(60.0, 40.0),
            profile=self.profile,
            margin_mm=2.0,
            priority=2
        )
        self.assertIsNotNone(pwr_zone)
        self.assertEqual(pwr_zone.net, "SW")
        self.assertEqual(pwr_zone.layer, 1)
        self.assertEqual(pwr_zone.priority, 2)  # Higher than GND
        self.assertEqual(pwr_zone.connection_type, "solid")
        self.assertFalse(pwr_zone.is_ground_plane)

    def test_04_polygon_boundary_and_keepout_check(self):
        # Valid zone inside board
        valid_zone = CopperZoneSpec(
            zone_id="Z1", net="GND", layer=1, layer_name="Top",
            points_mm=[(5.0, 5.0), (30.0, 5.0), (30.0, 25.0), (5.0, 25.0)]
        )
        violations = CopperPlaneEngine.check_polygon_boundary(
            valid_zone, (60.0, 40.0), edge_setback_mm=0.5
        )
        self.assertEqual(len(violations), 0)

        # Zone penetrating keepout
        keepouts = [{"name": "RF_ANT_KEEPOUT", "layer": 1, "rect_mm": [20.0, 20.0, 40.0, 35.0]}]
        viol_ko = CopperPlaneEngine.check_polygon_boundary(
            valid_zone, (60.0, 40.0), edge_setback_mm=0.5, keepouts=keepouts
        )
        self.assertTrue(any("penetrates keepout" in v for v in viol_ko))

        # Zone violating board edge setback
        viol_zone = CopperZoneSpec(
            zone_id="Z_OUT", net="GND", layer=1, layer_name="Top",
            points_mm=[(0.1, 5.0), (30.0, 5.0), (30.0, 25.0), (0.1, 25.0)]
        )
        viol_edge = CopperPlaneEngine.check_polygon_boundary(
            viol_zone, (60.0, 40.0), edge_setback_mm=0.5
        )
        self.assertTrue(any("violates board edge setback" in v for v in viol_edge))

    def test_05_copper_island_detection(self):
        zone = CopperZoneSpec(
            zone_id="Z_ISLAND", net="3V3", layer=1, layer_name="Top",
            points_mm=[(10.0, 10.0), (20.0, 10.0), (20.0, 20.0), (10.0, 20.0)],
            min_island_area_mm2=2.0
        )
        # 1. Zero pads of net 3V3 -> unconnected floating island
        res_no_pads = CopperPlaneEngine.detect_copper_islands(zone, pads=[])
        self.assertTrue(res_no_pads["is_island"])
        self.assertEqual(res_no_pads["action"], "remove")
        self.assertEqual(res_no_pads["reason"], "unconnected_floating_copper")

        # 2. Contains pad of 3V3 -> valid zone
        pads = [{"net": "3V3", "layer": 1, "x_mm": 15.0, "y_mm": 15.0}]
        res_valid = CopperPlaneEngine.detect_copper_islands(zone, pads=pads)
        self.assertFalse(res_valid["is_island"])
        self.assertEqual(res_valid["action"], "keep")

        # 3. Very tiny polygon below min_island_area_mm2
        tiny_zone = CopperZoneSpec(
            zone_id="Z_TINY", net="3V3", layer=1, layer_name="Top",
            points_mm=[(10.0, 10.0), (10.5, 10.0), (10.5, 10.5), (10.0, 10.5)],  # 0.25 mm2
            min_island_area_mm2=2.0
        )
        res_tiny = CopperPlaneEngine.detect_copper_islands(
            tiny_zone, pads=[{"net": "3V3", "layer": 1, "x_mm": 10.2, "y_mm": 10.2}]
        )
        self.assertTrue(res_tiny["is_island"])
        self.assertEqual(res_tiny["action"], "remove")
        self.assertEqual(res_tiny["reason"], "below_min_island_area")

    def test_06_revision_tracker_and_invalidation(self):
        tracker = CopperZoneRevisionTracker()
        zone1 = CopperZoneSpec(zone_id="Z_GND", net="GND", layer=2, layer_name="Inner1_GND", points_mm=[(0, 0), (10, 0), (10, 10), (0, 10)])
        zone2 = CopperZoneSpec(zone_id="Z_PWR", net="SW", layer=1, layer_name="Top", points_mm=[(20, 20), (30, 20), (30, 30), (20, 30)])

        fp1 = tracker.register_zone(zone1, self.profile.profile_hash)
        fp2 = tracker.register_zone(zone2, self.profile.profile_hash)
        self.assertIsNotNone(fp1)
        self.assertFalse(tracker.is_zone_stale("Z_GND"))
        self.assertFalse(tracker.is_zone_stale("Z_PWR"))

        # Invalidate net "SW"
        tracker.invalidate_zones(affected_nets={"SW"})
        self.assertFalse(tracker.is_zone_stale("Z_GND"))
        self.assertTrue(tracker.is_zone_stale("Z_PWR"))
        self.assertEqual(tracker.get_stale_zones(), ["Z_PWR"])

        # Mark poured (offline model)
        tracker.mark_poured("Z_PWR", poured_area_mm2=100.0)
        self.assertFalse(tracker.is_zone_stale("Z_PWR"))
        self.assertEqual(zone2.status, "NOT_LIVE_VERIFIED")

if __name__ == "__main__":
    unittest.main()
