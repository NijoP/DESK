"""Offline tests for desk/copper_fill.py (API-only plane copper)."""
import unittest

try:
    import shapely  # noqa: F401
    HAVE_SHAPELY = True
except ImportError:
    HAVE_SHAPELY = False

MIL = 39.37007874


@unittest.skipUnless(HAVE_SHAPELY, "shapely not installed")
class TestCopperFill(unittest.TestCase):
    def setUp(self):
        from desk import copper_fill as cf
        self.cf = cf
        self.board = [(0, 0), (20, 0), (20, 10), (0, 10)]
        self.via = [{"net": "GND", "x": 2 * MIL, "y": 2 * MIL, "d": 0.6 * MIL}]
        self.track = [{"net": "SIG", "layer": 1, "x1": 10 * MIL, "y1": 0.5 * MIL, "x2": 10 * MIL, "y2": 9.5 * MIL, "w": 0.2 * MIL}]

    def test_clearance_to_other_net_track(self):
        from shapely.geometry import LineString
        r = self.cf.compute_plane_fill(1, "GND", self.board, [], self.track, self.via, clearance_mm=0.3, simplify_mm=0)
        seg = LineString([(10, 0.5), (10, 9.5)])
        for p in r["polygons"]:
            self.assertGreaterEqual(p.distance(seg) - 0.1, 0.3 - 1e-6)

    def test_piece_without_via_is_pruned(self):
        # the full-height track splits the board; only the left half holds a GND via
        r = self.cf.compute_plane_fill(1, "GND", self.board, [], self.track, self.via, clearance_mm=0.3)
        self.assertEqual(len(r["polygons"]), 1)
        self.assertLess(r["polygons"][0].bounds[2], 10)
        self.assertEqual(r["removed_islands"], 1)

    def test_complex_polygon_source(self):
        r = self.cf.compute_plane_fill(1, "GND", self.board, [], [], self.via, clearance_mm=0.3)
        src = self.cf.polygon_to_easyeda_complex(r["polygons"][0])
        self.assertEqual(src[0][2], "L")
        self.assertEqual(src[0][:2], src[0][-2:])   # closed ring

    def test_explicit_link_avoids_blocked_target(self):
        from shapely.geometry import LineString
        wall = LineString([(5, -1), (5, 1)]).buffer(0.1)          # other-net track between start and the near via
        t = self.cf.explicit_link((4, 0), [(6, 0), (4, 3)], wall, clearance_mm=0.2, width_mm=0.25)
        self.assertEqual(t, (4.0, 3.0))                            # nearer (6,0) is blocked, (4,3) is reachable
        self.assertIsNone(self.cf.explicit_link((4, 0), [(6, 0)], wall, 0.2, 0.25))
        self.assertIsNone(self.cf.explicit_link((4, 0), [(40, 0)], None, 0.2, 0.25))   # beyond max length

    def test_absolute_polygon_pad_is_not_rotated_again(self):
        # USB-C J1 A4B9 readback (Plotus run 2b): absolute, already-rotated polygon 1.3 x 0.6 mm, pad rot -90
        pad = {"x": 302.1294, "y": 960.6317, "rot": -90.0,
               "shape": ["POLYGON", [276.5374, 948.8177, "L", 276.5374, 972.4387, 327.7164, 972.4387, 327.7164, 948.8177]]}
        x0, y0, x1, y1 = self.cf.pad_geometry(pad).bounds
        self.assertAlmostEqual(x1 - x0, 1.3, places=2)
        self.assertAlmostEqual(y1 - y0, 0.6, places=2)


if __name__ == "__main__":
    unittest.main()
