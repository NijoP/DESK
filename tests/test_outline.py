import unittest

from desk.routing.outline import rect_outline_polygon, corner_keepouts, outline_create_js, validate_outline_primitives, MIL


class TestOutline(unittest.TestCase):
    def test_plain_r_polygon(self):
        p = rect_outline_polygon(30.0, 45.0)
        self.assertEqual(p[0], "R")
        self.assertAlmostEqual(p[3], 30.0 * MIL, places=3)
        self.assertAlmostEqual(p[4], 45.0 * MIL, places=3)
        self.assertEqual((p[5], p[6]), (0, 0))

    def test_corner_keepouts_cover_four_corners(self):
        ks = corner_keepouts(30.0, 45.0, 3.0)
        self.assertEqual(len(ks), 4)
        self.assertEqual(ks[3]["rect_mm"], [27.0, 42.0, 30.0, 45.0])

    def test_js_never_sends_a_vertex_list(self):
        js = outline_create_js(30.0, 45.0)
        self.assertIn('createPolygon(["R"', js)
        self.assertIn("pcb_PrimitivePolyline.create(11", js)
        self.assertNotIn("[[", js)

    def test_validation(self):
        self.assertEqual(validate_outline_primitives([{"id": "a", "layer": 11, "closed": True, "polygon": ["R", 0, 0, 10, 10, 0, 0]}]), [])
        self.assertTrue(validate_outline_primitives([{"id": str(i), "layer": 11} for i in range(36)]))
        self.assertTrue(validate_outline_primitives([{"id": "a", "layer": 11, "polygon": ["R", 0, 0, 10, 10, 3, 3]}]))
        self.assertTrue(validate_outline_primitives([{"id": "a", "layer": 11, "polygon": [0, 0] * 40}]))


if __name__ == "__main__":
    unittest.main()
