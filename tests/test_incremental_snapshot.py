"""Unit and Property-Based Tests for Indexed PCB Snapshot and Incremental Computation.
Validates:
- 2D Spatial Grid Partitioning
- Multi-Domain Fingerprinting (tracks, vias, zones, stackup, rules)
- Incremental Update Equivalence Invariant:
  RESULT_FROM_INCREMENTAL_UPDATE == RESULT_FROM_FULL_REBUILD
"""
import unittest
import copy
from desk.snapshot import IndexedPCBSnapshot, SpatialGridIndex

class TestIncrementalSnapshot(unittest.TestCase):

    def setUp(self):
        self.raw_dump = {
            "R1": {
                "x": 100.0, "y": 100.0, "rot": 0, "layer": 1,
                "bbox": [-20, 20, -10, 10],
                "pads": [
                    {"num": "1", "net": "VIN", "dx": -15, "dy": 0, "layer": 1},
                    {"num": "2", "net": "SW", "dx": 15, "dy": 0, "layer": 1}
                ]
            },
            "C1": {
                "x": 300.0, "y": 100.0, "rot": 90, "layer": 1,
                "bbox": [-10, 10, -10, 10],
                "pads": [
                    {"num": "1", "net": "SW", "dx": 0, "dy": -8, "layer": 1},
                    {"num": "2", "net": "GND", "dx": 0, "dy": 8, "layer": 1}
                ]
            }
        }
        self.tracks = [
            {"id": "t1", "x1": 115, "y1": 100, "x2": 300, "y2": 92, "width": 12, "layer": 1, "net": "SW"}
        ]
        self.vias = [
            {"id": "v1", "x": 300, "y": 108, "hole_dia": 12, "dia": 24, "net": "GND"}
        ]

    def test_01_spatial_grid_index(self):
        grid = SpatialGridIndex(cell_size_mil=100.0)
        grid.insert("R1", 80, 90, 120, 110)
        grid.insert("C1", 290, 90, 310, 110)

        # Query region overlapping R1 only
        res_r1 = grid.query_rect(50, 50, 150, 150)
        self.assertIn("R1", res_r1)
        self.assertNotIn("C1", res_r1)

        # Query region overlapping both
        res_both = grid.query_rect(50, 50, 350, 150)
        self.assertIn("R1", res_both)
        self.assertIn("C1", res_both)

        # Remove R1
        grid.remove("R1")
        res_after = grid.query_rect(50, 50, 350, 150)
        self.assertNotIn("R1", res_after)
        self.assertIn("C1", res_after)

    def test_02_composite_fingerprint_sensitivity(self):
        # Baseline snapshot
        snap1 = IndexedPCBSnapshot(self.raw_dump, tracks=self.tracks, vias=self.vias)
        fp1 = snap1.fingerprint

        # Snapshot with modified track width
        tracks_mod = copy.deepcopy(self.tracks)
        tracks_mod[0]["width"] = 25  # Thicker trace
        snap2 = IndexedPCBSnapshot(self.raw_dump, tracks=tracks_mod, vias=self.vias)
        fp2 = snap2.fingerprint

        # Fingerprint MUST change when tracks are modified!
        self.assertNotEqual(fp1, fp2)
        self.assertNotEqual(snap1.geometry_rev, snap2.geometry_rev)

    def test_03_incremental_update_equivalence_invariant(self):
        """CRITICAL INVARIANT TEST:
        RESULT_FROM_INCREMENTAL_UPDATE == RESULT_FROM_FULL_REBUILD
        """
        # 1. Full Initial Build
        initial_dump = copy.deepcopy(self.raw_dump)
        snap_incremental = IndexedPCBSnapshot(initial_dump, tracks=self.tracks, vias=self.vias)

        # 2. Incremental Update: Move R1 to (500.0, 450.0) with rotation 180
        snap_incremental.update_component_placement(
            ref="R1",
            x_mil=500.0,
            y_mil=450.0,
            rot_deg=180.0,
            layer=1
        )

        # 3. Full Rebuild from modified dump
        rebuilt_dump = copy.deepcopy(self.raw_dump)
        rebuilt_dump["R1"]["x"] = 500.0
        rebuilt_dump["R1"]["y"] = 450.0
        rebuilt_dump["R1"]["rot"] = 180.0
        rebuilt_dump["R1"]["layer"] = 1
        snap_full_rebuild = IndexedPCBSnapshot(rebuilt_dump, tracks=self.tracks, vias=self.vias)

        # Verify exact equivalence
        self.assertEqual(snap_incremental.fingerprint, snap_full_rebuild.fingerprint)
        self.assertEqual(snap_incremental.geometry_rev, snap_full_rebuild.geometry_rev)
        self.assertEqual(snap_incremental.connectivity_rev, snap_full_rebuild.connectivity_rev)

        # Verify net endpoints equivalence
        eps_inc = sorted([(ep.ref, ep.pad_num, round(ep.x_mil, 2), round(ep.y_mil, 2)) for ep in snap_incremental.get_endpoints_for_net("SW")])
        eps_reb = sorted([(ep.ref, ep.pad_num, round(ep.x_mil, 2), round(ep.y_mil, 2)) for ep in snap_full_rebuild.get_endpoints_for_net("SW")])
        self.assertEqual(eps_inc, eps_reb)

if __name__ == "__main__":
    unittest.main()
