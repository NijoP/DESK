import unittest

from desk.routing.outline import rect_outline_polygon, corner_keepouts, outline_create_js, validate_outline_primitives, MIL


class TestOutline(unittest.TestCase):
    def test_plain_r_polygon(self):
        p = rect_outline_polygon(30.0, 45.0)
        self.assertEqual(p[0], "R")
        self.assertAlmostEqual(p[3], 30.0 * MIL, places=3)
        self.assertAlmostEqual(p[4], 45.0 * MIL, places=3)
        self.assertEqual((p[5], p[6]), (0, 0))

    def test_r_polygon_y_is_top_edge(self):
        # EasyEDA "R": (x, y) is the TOP-left corner (Plotus run 1 F-009: origin used as bottom-left drew 0..-44 mm)
        p = rect_outline_polygon(74.0, 44.0)
        self.assertAlmostEqual(p[1], 0.0, places=3)
        self.assertAlmostEqual(p[2], 44.0 * MIL, places=3)
        p = rect_outline_polygon(10.0, 5.0, origin_mm=(2.0, 3.0))
        self.assertAlmostEqual(p[1], 2.0 * MIL, places=3)
        self.assertAlmostEqual(p[2], 8.0 * MIL, places=3)

    def test_radius_goes_in_field_7_rotation_stays_zero(self):
        # Plotus run 2b R2-F-007 readback: ["R", 0, 1732.2835, 2913.3858, 1732.2835, 0, 78.7402] = 74 x 44 mm, r 2 mm
        p = rect_outline_polygon(74.0, 44.0, radius_mm=2.0)
        self.assertEqual(p[5], 0)
        self.assertAlmostEqual(p[6], 78.7402, places=3)
        for got, want in zip(p[1:], [0.0, 1732.2835, 2913.3858, 1732.2835, 0, 78.7402]):
            self.assertAlmostEqual(got, want, places=3)
        with self.assertRaises(ValueError):
            rect_outline_polygon(10.0, 5.0, radius_mm=3.0)

    def test_corner_keepouts_cover_four_corners(self):
        ks = corner_keepouts(30.0, 45.0, 3.0)
        self.assertEqual(len(ks), 4)
        self.assertEqual(ks[3]["rect_mm"], [27.0, 42.0, 30.0, 45.0])

    def test_js_never_sends_a_vertex_list(self):
        js = outline_create_js(30.0, 45.0)
        self.assertIn('createPolygon(["R"', js)
        self.assertNotIn("[[", js)

    def test_js_uses_live_create_signature(self):
        # live: create(net, layer, polygon, lineWidth, primitiveLock); create(layer, polygon, 0, 0) failed (run 1 F-008)
        js = outline_create_js(74.0, 44.0, radius_mm=2.0)
        self.assertIn("pcb_PrimitivePolyline.create('', 11, __poly, 10.0, false)", js)
        self.assertIn("78.7402]", js)

    def test_validation(self):
        self.assertEqual(validate_outline_primitives([{"id": "a", "layer": 11, "closed": True, "polygon": ["R", 0, 0, 10, 10, 0, 0]}]), [])
        self.assertEqual(validate_outline_primitives([{"id": "a", "layer": 11, "polygon": ["R", 0, 1732, 2913, 1732, 0, 78.74]}]), [])
        self.assertTrue(validate_outline_primitives([{"id": str(i), "layer": 11} for i in range(36)]))
        self.assertTrue(validate_outline_primitives([{"id": "a", "layer": 11, "polygon": ["R", 0, 0, 10, 10, 3, 3]}]))   # rotated
        self.assertTrue(validate_outline_primitives([{"id": "a", "layer": 11, "polygon": ["R", 0, 10, 10, 10, 0, 6]}]))  # radius too big
        self.assertTrue(validate_outline_primitives([{"id": "a", "layer": 11, "polygon": [0, 0] * 40}]))


if __name__ == "__main__":
    unittest.main()
