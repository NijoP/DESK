"""Dump pad offsets are board-frame (QA-03): no double rotation anywhere in the geometry stack."""
import math
import unittest

from desk.routing.connectivity import pad_xy, pad_size_mil
from desk.routing.board import BoardIntelligenceEngine
from desk.routability import RoutabilityEvaluator
from desk.routing.preflight import pads_inside_keepouts

MIL = 39.37007874


def rotated_part(ref="U1", rot=90):
    # A part rotated 90 deg whose pad already sits at board-frame offset (0, +100 mil), as pcb_dump.py stores it.
    return {ref: {"x": 1000.0, "y": 1000.0, "rot": rot, "layer": 1, "fp": "T", "bbox": [-50, 50, -120, 120],
                  "pads": [{"num": "1", "dx": 0.0, "dy": 100.0, "shape": ["RECT", 30, 40, 0], "rot": rot, "net": "A", "layer": 1}]}}


class TestPadFrame(unittest.TestCase):
    def test_pad_xy_uses_offsets_as_is(self):
        comp = rotated_part()["U1"]
        self.assertEqual(pad_xy(comp, comp["pads"][0]), (1000.0, 1100.0))

    def test_pad_xy_applies_only_the_delta_to_a_planned_rotation(self):
        comp = rotated_part(rot=90)["U1"]
        x, y = pad_xy(comp, comp["pads"][0], rot_override=180)   # +90 deg delta: (0,100) -> (-100, 0)
        self.assertAlmostEqual(x, 900.0, places=6)
        self.assertAlmostEqual(y, 1000.0, places=6)
        x2, y2 = pad_xy(comp, comp["pads"][0], rot_override=90)  # no delta
        self.assertEqual((x2, y2), (1000.0, 1100.0))

    def test_pad_size_from_shape(self):
        self.assertEqual(pad_size_mil({"shape": ["RECT", 31.5, 35.4, 0]}), (31.5, 35.4))
        self.assertEqual(pad_size_mil({"w": 10, "h": 12}), (10.0, 12.0))
        self.assertEqual(pad_size_mil({}), (15.0, 15.0))

    def test_board_model_and_graph_agree_with_pad_xy(self):
        dump = rotated_part()
        board = BoardIntelligenceEngine(2000, 2000, ["Top", "Bottom"], dump)
        p = board.pads["U1.1"]
        self.assertEqual((p.x_mil, p.y_mil), (1000.0, 1100.0))
        self.assertEqual((p.width_mil, p.height_mil), (30.0, 40.0))
        dump2 = {**rotated_part("U1"), **rotated_part("U2")}
        dump2["U2"]["x"] = 1500.0
        g = RoutabilityEvaluator.build_connectivity_graph(dump2)
        eps = {(e.ref, e.x_mil, e.y_mil) for e in g.nets["A"]}
        self.assertEqual(eps, {("U1", 1000.0, 1100.0), ("U2", 1500.0, 1100.0)})

    def test_keepout_check_uses_board_frame(self):
        dump = rotated_part()
        # pad at (1000, 1100) mil = (25.4, 27.94) mm; a keep-out around that point must catch it
        hits = pads_inside_keepouts(dump, [{"name": "k", "rect_mm": [25.0, 27.5, 26.0, 28.5], "side": "both", "allow": []}])
        self.assertEqual(hits, ["U1.1 in keep-out 'k'"])
        # the double-rotated position (900, 1000) mil = (22.9, 25.4) mm must NOT be flagged
        miss = pads_inside_keepouts(dump, [{"name": "k", "rect_mm": [22.5, 25.0, 23.5, 26.0], "side": "both", "allow": []}])
        self.assertEqual(miss, [])


if __name__ == "__main__":
    unittest.main()
