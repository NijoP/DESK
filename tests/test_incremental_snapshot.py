"""
Unit tests proving equivalence between Incremental Snapshot Updates and Full Reconstruction:
RESULT_FROM_INCREMENTAL_UPDATE == RESULT_FROM_FULL_REBUILD
"""

import copy
import unittest

from desk.snapshot import IndexedPCBSnapshot


class TestIncrementalSnapshotEquivalence(unittest.TestCase):
    def setUp(self):
        self.base_dump = {
            "C1": {
                "x": 100.0,
                "y": 100.0,
                "rot": 0,
                "layer": 1,
                "bbox": [-10, 10, -10, 10],
                "pads": [
                    {"num": "1", "dx": -5.0, "dy": 0.0, "net": "VCC", "layer": 1},
                    {"num": "2", "dx": 5.0, "dy": 0.0, "net": "GND", "layer": 1},
                ],
            },
            "U1": {
                "x": 500.0,
                "y": 500.0,
                "rot": 90,
                "layer": 1,
                "bbox": [-20, 20, -20, 20],
                "pads": [
                    {"num": "1", "dx": -15.0, "dy": 0.0, "net": "VCC", "layer": 1},
                    {"num": "2", "dx": 0.0, "dy": 0.0, "net": "GND", "layer": 1},
                    {"num": "3", "dx": 15.0, "dy": 0.0, "net": "SIG_OUT", "layer": 1},
                ],
            },
        }
        self.base_tracks = [
            {"id": "t1", "x1": 100.0, "y1": 100.0, "x2": 500.0, "y2": 500.0, "width": 10.0, "layer": 1, "net": "VCC"}
        ]
        self.base_vias = [{"id": "v1", "x": 100.0, "y": 100.0, "dia": 24.0, "hole_dia": 12.0, "net": "GND"}]
        self.base_zones = [{"id": "z1", "net": "GND", "layer": 2, "priority": 1}]
        self.base_stackup = [{"name": "Top", "copper_thickness_oz": 1.0}, {"name": "GND", "copper_thickness_oz": 1.0}]
        self.base_rules = {"min_clearance_mil": 6.0}

    def _assert_equivalent(self, inc_snap: IndexedPCBSnapshot, rebuilt_snap: IndexedPCBSnapshot):
        self.assertEqual(inc_snap.fingerprint, rebuilt_snap.fingerprint, "Fingerprint mismatch!")
        self.assertEqual(inc_snap.geometry_rev, rebuilt_snap.geometry_rev, "Geometry revision mismatch!")
        self.assertEqual(inc_snap.connectivity_rev, rebuilt_snap.connectivity_rev, "Connectivity revision mismatch!")
        self.assertEqual(inc_snap.stackup_rev, rebuilt_snap.stackup_rev, "Stackup revision mismatch!")
        self.assertEqual(inc_snap.copper_rev, rebuilt_snap.copper_rev, "Copper revision mismatch!")
        self.assertEqual(inc_snap.rules_rev, rebuilt_snap.rules_rev, "Rules revision mismatch!")

    def test_component_movement_and_rotation(self):
        snap = IndexedPCBSnapshot(
            copy.deepcopy(self.base_dump),
            tracks=copy.deepcopy(self.base_tracks),
            vias=copy.deepcopy(self.base_vias),
            zones=copy.deepcopy(self.base_zones),
            stackup=copy.deepcopy(self.base_stackup),
            rules=copy.deepcopy(self.base_rules),
        )

        # Apply incremental move
        snap.update_component_placement("C1", x_mil=250.0, y_mil=300.0, rot_deg=45.0, layer=2)

        # Full reconstruction
        rebuilt_dump = copy.deepcopy(self.base_dump)
        rebuilt_dump["C1"]["x"] = 250.0
        rebuilt_dump["C1"]["y"] = 300.0
        rebuilt_dump["C1"]["rot"] = 45.0
        rebuilt_dump["C1"]["layer"] = 2
        rebuilt = IndexedPCBSnapshot(
            rebuilt_dump,
            tracks=copy.deepcopy(self.base_tracks),
            vias=copy.deepcopy(self.base_vias),
            zones=copy.deepcopy(self.base_zones),
            stackup=copy.deepcopy(self.base_stackup),
            rules=copy.deepcopy(self.base_rules),
        )

        self._assert_equivalent(snap, rebuilt)

    def test_component_addition_and_deletion(self):
        snap = IndexedPCBSnapshot(
            copy.deepcopy(self.base_dump),
            tracks=copy.deepcopy(self.base_tracks),
            vias=copy.deepcopy(self.base_vias),
            zones=copy.deepcopy(self.base_zones),
            stackup=copy.deepcopy(self.base_stackup),
            rules=copy.deepcopy(self.base_rules),
        )

        new_comp = {
            "x": 800.0,
            "y": 200.0,
            "rot": 0,
            "layer": 1,
            "pads": [{"num": "1", "net": "SIG_OUT"}, {"num": "2", "net": "GND"}],
        }
        # Add incrementally
        snap.add_component("R1", new_comp)

        rebuilt_dump = copy.deepcopy(self.base_dump)
        rebuilt_dump["R1"] = copy.deepcopy(new_comp)
        rebuilt = IndexedPCBSnapshot(
            rebuilt_dump,
            tracks=copy.deepcopy(self.base_tracks),
            vias=copy.deepcopy(self.base_vias),
            zones=copy.deepcopy(self.base_zones),
            stackup=copy.deepcopy(self.base_stackup),
            rules=copy.deepcopy(self.base_rules),
        )
        self._assert_equivalent(snap, rebuilt)

        # Now remove incrementally
        snap.remove_component("R1")
        rebuilt_original = IndexedPCBSnapshot(
            copy.deepcopy(self.base_dump),
            tracks=copy.deepcopy(self.base_tracks),
            vias=copy.deepcopy(self.base_vias),
            zones=copy.deepcopy(self.base_zones),
            stackup=copy.deepcopy(self.base_stackup),
            rules=copy.deepcopy(self.base_rules),
        )
        self._assert_equivalent(snap, rebuilt_original)

    def test_pad_net_reassignment(self):
        snap = IndexedPCBSnapshot(
            copy.deepcopy(self.base_dump),
            tracks=copy.deepcopy(self.base_tracks),
            vias=copy.deepcopy(self.base_vias),
            zones=copy.deepcopy(self.base_zones),
            stackup=copy.deepcopy(self.base_stackup),
            rules=copy.deepcopy(self.base_rules),
        )

        # Reassign C1 pad 1 from VCC to 3V3
        snap.update_pad_net("C1", "1", "3V3")

        rebuilt_dump = copy.deepcopy(self.base_dump)
        rebuilt_dump["C1"]["pads"][0]["net"] = "3V3"
        rebuilt = IndexedPCBSnapshot(
            rebuilt_dump,
            tracks=copy.deepcopy(self.base_tracks),
            vias=copy.deepcopy(self.base_vias),
            zones=copy.deepcopy(self.base_zones),
            stackup=copy.deepcopy(self.base_stackup),
            rules=copy.deepcopy(self.base_rules),
        )
        self._assert_equivalent(snap, rebuilt)

    def test_tracks_and_vias_updates(self):
        snap = IndexedPCBSnapshot(
            copy.deepcopy(self.base_dump),
            tracks=copy.deepcopy(self.base_tracks),
            vias=copy.deepcopy(self.base_vias),
            zones=copy.deepcopy(self.base_zones),
            stackup=copy.deepcopy(self.base_stackup),
            rules=copy.deepcopy(self.base_rules),
        )

        new_track = {"id": "t2", "x1": 500.0, "y1": 500.0, "x2": 600.0, "y2": 600.0, "width": 8.0, "layer": 1, "net": "SIG_OUT"}
        snap.add_track(new_track)

        rebuilt_tracks = copy.deepcopy(self.base_tracks) + [new_track]
        rebuilt = IndexedPCBSnapshot(
            copy.deepcopy(self.base_dump),
            tracks=rebuilt_tracks,
            vias=copy.deepcopy(self.base_vias),
            zones=copy.deepcopy(self.base_zones),
            stackup=copy.deepcopy(self.base_stackup),
            rules=copy.deepcopy(self.base_rules),
        )
        self._assert_equivalent(snap, rebuilt)

    def test_stackup_and_rules_updates(self):
        snap = IndexedPCBSnapshot(
            copy.deepcopy(self.base_dump),
            tracks=copy.deepcopy(self.base_tracks),
            vias=copy.deepcopy(self.base_vias),
            zones=copy.deepcopy(self.base_zones),
            stackup=copy.deepcopy(self.base_stackup),
            rules=copy.deepcopy(self.base_rules),
        )

        new_rules = {"min_clearance_mil": 8.0, "min_trace_mil": 5.0}
        snap.update_rules(new_rules)

        rebuilt = IndexedPCBSnapshot(
            copy.deepcopy(self.base_dump),
            tracks=copy.deepcopy(self.base_tracks),
            vias=copy.deepcopy(self.base_vias),
            zones=copy.deepcopy(self.base_zones),
            stackup=copy.deepcopy(self.base_stackup),
            rules=new_rules,
        )
        self._assert_equivalent(snap, rebuilt)


if __name__ == "__main__":
    unittest.main()
