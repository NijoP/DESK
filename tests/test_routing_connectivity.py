"""Automated Verification Suite for Physical Pad-to-Pad Connectivity Engine.
Tests continuous copper graph construction, T-junction detection, via hops,
and connected component isolation.
"""
import unittest
from desk.routing.connectivity import (
    PhysicalConnectivityVerifier,
    _dist_point_to_segment,
    _segments_overlap_or_touch,
)


class TestRoutingConnectivity(unittest.TestCase):

    def test_point_to_segment_distance(self):
        # Point on segment
        d, px, py = _dist_point_to_segment(5.0, 0.0, 0.0, 0.0, 10.0, 0.0)
        self.assertAlmostEqual(d, 0.0)
        self.assertAlmostEqual(px, 5.0)
        self.assertAlmostEqual(py, 0.0)

        # Point perpendicular to segment
        d, px, py = _dist_point_to_segment(5.0, 3.0, 0.0, 0.0, 10.0, 0.0)
        self.assertAlmostEqual(d, 3.0)
        self.assertAlmostEqual(px, 5.0)

        # Point beyond segment endpoint
        d, px, py = _dist_point_to_segment(14.0, 3.0, 0.0, 0.0, 10.0, 0.0)
        self.assertAlmostEqual(d, 5.0)  # sqrt(4^2 + 3^2)

    def test_segments_touch_and_t_junction(self):
        # Collinear touching segments
        s1 = (0.0, 0.0, 10.0, 0.0, 6.0)
        s2 = (10.0, 0.0, 20.0, 0.0, 6.0)
        self.assertTrue(_segments_overlap_or_touch(s1, s2))

        # T-junction: s2 ends on s1 middle
        s3 = (5.0, 0.0, 5.0, 10.0, 6.0)
        self.assertTrue(_segments_overlap_or_touch(s1, s3))

        # Parallel disjoint segments beyond clearance
        s4 = (0.0, 20.0, 10.0, 20.0, 6.0)
        self.assertFalse(_segments_overlap_or_touch(s1, s4))

    def test_fully_connected_two_terminal_net(self):
        dump = {
            "U1": {"x": 100.0, "y": 100.0, "rot": 0, "layer": 1,
                   "pads": [{"num": "1", "net": "NET_A", "dx": 0.0, "dy": 0.0, "w": 20.0, "h": 20.0, "layer": 1}]},
            "R1": {"x": 200.0, "y": 100.0, "rot": 0, "layer": 1,
                   "pads": [{"num": "1", "net": "NET_A", "dx": 0.0, "dy": 0.0, "w": 20.0, "h": 20.0, "layer": 1}]}
        }
        # Continuous track from U1.1 (100, 100) to R1.1 (200, 100)
        tracks = [
            {"net": "NET_A", "start_x": 100.0, "start_y": 100.0, "end_x": 200.0, "end_y": 100.0, "width": 8.0, "layer": 1}
        ]

        res = PhysicalConnectivityVerifier.verify_board(dump, tracks)
        self.assertEqual(res.fully_connected_nets, 1)
        self.assertTrue(res.is_100_percent_routed)
        self.assertEqual(res.net_reports["NET_A"].status, "FULLY_CONNECTED")

    def test_partially_connected_and_unconnected_pads(self):
        dump = {
            "U1": {"x": 100.0, "y": 100.0, "rot": 0, "layer": 1,
                   "pads": [{"num": "1", "net": "NET_B", "dx": 0.0, "dy": 0.0, "w": 20.0, "h": 20.0, "layer": 1}]},
            "R1": {"x": 200.0, "y": 100.0, "rot": 0, "layer": 1,
                   "pads": [{"num": "1", "net": "NET_B", "dx": 0.0, "dy": 0.0, "w": 20.0, "h": 20.0, "layer": 1}]},
            "C1": {"x": 300.0, "y": 100.0, "rot": 0, "layer": 1,
                   "pads": [{"num": "1", "net": "NET_B", "dx": 0.0, "dy": 0.0, "w": 20.0, "h": 20.0, "layer": 1}]}
        }
        # Track connects only U1.1 to R1.1; C1.1 is dangling
        tracks = [
            {"net": "NET_B", "start_x": 100.0, "start_y": 100.0, "end_x": 200.0, "end_y": 100.0, "width": 8.0, "layer": 1}
        ]

        res = PhysicalConnectivityVerifier.verify_board(dump, tracks)
        self.assertEqual(res.fully_connected_nets, 0)
        self.assertEqual(res.partially_connected_nets, 1)
        self.assertFalse(res.is_100_percent_routed)
        report = res.net_reports["NET_B"]
        self.assertEqual(report.status, "PARTIALLY_CONNECTED")
        self.assertIn("C1.1", report.unconnected_pads)

    def test_via_layer_hopping_connectivity(self):
        # Pad 1 on Top Layer (1), Pad 2 on Bottom Layer (2)
        dump = {
            "U1": {"x": 100.0, "y": 100.0, "rot": 0, "layer": 1,
                   "pads": [{"num": "1", "net": "NET_V", "dx": 0.0, "dy": 0.0, "w": 20.0, "h": 20.0, "layer": 1}]},
            "U2": {"x": 300.0, "y": 100.0, "rot": 0, "layer": 2,
                   "pads": [{"num": "1", "net": "NET_V", "dx": 0.0, "dy": 0.0, "w": 20.0, "h": 20.0, "layer": 2}]}
        }
        # Track 1 on layer 1 to Via at (200, 100)
        tracks = [
            {"net": "NET_V", "start_x": 100.0, "start_y": 100.0, "end_x": 200.0, "end_y": 100.0, "width": 8.0, "layer": 1},
            {"net": "NET_V", "start_x": 200.0, "start_y": 100.0, "end_x": 300.0, "end_y": 100.0, "width": 8.0, "layer": 2}
        ]
        vias = [
            {"net": "NET_V", "x": 200.0, "y": 100.0, "diameter": 24.0, "start_layer": 1, "end_layer": 2}
        ]

        res = PhysicalConnectivityVerifier.verify_board(dump, tracks, vias=vias)
        self.assertTrue(res.is_100_percent_routed)
        self.assertEqual(res.net_reports["NET_V"].status, "FULLY_CONNECTED")


if __name__ == "__main__":
    unittest.main()
