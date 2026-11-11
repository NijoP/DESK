"""Poured copper zones as conductors in the physical connectivity verifier (roadmap SW-11)."""
import unittest

from desk.routing.connectivity import PhysicalConnectivityVerifier, _span_covers, _layer_rank

MIL = 39.37007874


def comp(ref, x_mm, y_mm, net, layer=1, pad_layer=None):
    return {ref: {"x": x_mm * MIL, "y": y_mm * MIL, "rot": 0, "layer": layer, "fp": "T",
                  "pads": [{"num": "1", "dx": 0.0, "dy": 0.0, "shape": ["RECT", 30, 30, 0], "rot": 0, "net": net,
                            "layer": pad_layer if pad_layer is not None else layer, "w": 30, "h": 30}]}}


def rect(x0, y0, x1, y1):
    return [[x0 * MIL, y0 * MIL], [x1 * MIL, y0 * MIL], [x1 * MIL, y1 * MIL], [x0 * MIL, y1 * MIL]]


class TestLayerOrder(unittest.TestCase):
    def test_inner_layers_sit_between_top_and_bottom(self):
        self.assertLess(_layer_rank(1), _layer_rank(15))
        self.assertLess(_layer_rank(15), _layer_rank(16))
        self.assertLess(_layer_rank(16), _layer_rank(2))
        self.assertTrue(_span_covers(1, 2, 15))      # through via reaches Inner1
        self.assertTrue(_span_covers(1, 2, 16))
        self.assertFalse(_span_covers(1, 15, 2))     # blind via top->Inner1 does not reach bottom
        self.assertTrue(_span_covers(1, 15, 15))


class TestZones(unittest.TestCase):
    def test_two_pads_joined_only_by_a_top_pour(self):
        dump = {**comp("C1", 2, 2, "GND"), **comp("C2", 18, 18, "GND")}
        zone = [{"net": "GND", "layer": 1, "polygon": rect(0, 0, 20, 20)}]
        without = PhysicalConnectivityVerifier.verify_board(dump, [], vias=[], zones=[])
        self.assertEqual(without.net_reports["GND"].status, "MISSING_ROUTE")
        with_zone = PhysicalConnectivityVerifier.verify_board(dump, [], vias=[], zones=zone)
        self.assertEqual(with_zone.net_reports["GND"].status, "FULLY_CONNECTED")
        self.assertTrue(with_zone.is_100_percent_routed)

    def test_pad_outside_the_pour_stays_unconnected(self):
        dump = {**comp("C1", 2, 2, "GND"), **comp("C2", 18, 18, "GND"), **comp("C3", 30, 30, "GND")}
        zone = [{"net": "GND", "layer": 1, "polygon": rect(0, 0, 20, 20)}]
        res = PhysicalConnectivityVerifier.verify_board(dump, [], vias=[], zones=zone)
        r = res.net_reports["GND"]
        self.assertEqual(r.status, "PARTIALLY_CONNECTED")
        self.assertIn("C3.1", r.unconnected_pads)

    def test_inner_plane_reached_through_vias(self):
        # SMD pads on top, GND plane on Inner1 (layer 15); each pad has a through via next to it inside the plane.
        dump = {**comp("C1", 2, 2, "GND"), **comp("C2", 18, 18, "GND")}
        zone = [{"net": "GND", "layer": 15, "polygon": rect(0, 0, 20, 20)}]
        vias = [{"net": "GND", "x": 2 * MIL + 20, "y": 2 * MIL, "diameter": 24, "start_layer": 1, "end_layer": 2},
                {"net": "GND", "x": 18 * MIL + 20, "y": 18 * MIL, "diameter": 24, "start_layer": 1, "end_layer": 2}]
        no_vias = PhysicalConnectivityVerifier.verify_board(dump, [], vias=[], zones=zone)
        self.assertNotEqual(no_vias.net_reports["GND"].status, "FULLY_CONNECTED")
        res = PhysicalConnectivityVerifier.verify_board(dump, [], vias=vias, zones=zone)
        self.assertEqual(res.net_reports["GND"].status, "FULLY_CONNECTED")

    def test_blind_via_does_not_reach_a_deeper_plane(self):
        dump = {**comp("C1", 2, 2, "GND"), **comp("C2", 18, 18, "GND")}
        zone = [{"net": "GND", "layer": 16, "polygon": rect(0, 0, 20, 20)}]
        vias = [{"net": "GND", "x": 2 * MIL + 20, "y": 2 * MIL, "diameter": 24, "start_layer": 1, "end_layer": 15},
                {"net": "GND", "x": 18 * MIL + 20, "y": 18 * MIL, "diameter": 24, "start_layer": 1, "end_layer": 15}]
        res = PhysicalConnectivityVerifier.verify_board(dump, [], vias=vias, zones=zone)
        self.assertNotEqual(res.net_reports["GND"].status, "FULLY_CONNECTED")

    def test_track_touching_a_pour(self):
        dump = {**comp("C1", 2, 2, "VBUS"), **comp("C2", 30, 2, "VBUS")}
        zone = [{"net": "VBUS", "layer": 1, "polygon": rect(10, 0, 20, 5)}]
        tracks = [{"net": "VBUS", "x1": 2 * MIL, "y1": 2 * MIL, "x2": 12 * MIL, "y2": 2 * MIL, "width": 10, "layer": 1},
                  {"net": "VBUS", "x1": 18 * MIL, "y1": 2 * MIL, "x2": 30 * MIL, "y2": 2 * MIL, "width": 10, "layer": 1}]
        res = PhysicalConnectivityVerifier.verify_board(dump, tracks, vias=[], zones=zone)
        self.assertEqual(res.net_reports["VBUS"].status, "FULLY_CONNECTED")
        no_zone = PhysicalConnectivityVerifier.verify_board(dump, tracks, vias=[], zones=[])
        self.assertNotEqual(no_zone.net_reports["VBUS"].status, "FULLY_CONNECTED")


if __name__ == "__main__":
    unittest.main()
