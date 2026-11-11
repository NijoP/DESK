"""Routing pre-flight gate (rework item A): planes, outline, pads inside router keep-outs."""
import unittest

from desk.routing.preflight import run_preflight, dsn_planes, dsn_boundary_closed, pads_inside_keepouts
from desk.routing.fixtures import make_board

MIL = 39.37007874

PLANE_GND = [[0.3, 0.3], [29.7, 0.3], [29.7, 44.7], [0.3, 44.7]]
PLANE_3V3 = [[0.3, 0.3], [29.7, 0.3], [29.7, 25.0], [0.3, 25.0]]


def poly(pts):
    return " ".join(f"{x * MIL:.2f} {y * MIL:.2f}" for x, y in pts)


SYNTHETIC_DSN = f"""(pcb board
  (structure
    (boundary (path signal 0 0 0 0 1771.65 1181.10 1771.65 1181.10 0 0 0))
    (layer TopLayer (type signal))
    (layer Inner1 (type signal))
    (plane GND (polygon Inner1 0 {poly(PLANE_GND)}))
    (plane 3V3 (polygon Inner2 0 {poly(PLANE_3V3)}))
  )
  (network (net GND (pins u1-a1 u1-b2)))
)"""


def plan_with(**kw):
    base = {"board_mm": [30.0, 45.0], "origin_mm": [0.0, 0.0],
            "planes": [{"net": "GND", "layer": "Inner1", "polygon_mm": PLANE_GND},
                       {"net": "3V3", "layer": "Inner2", "polygon_mm": PLANE_3V3}],
            "route_keepouts": [{"name": "antenna", "rect_mm": [6.6, 0.0, 25.6, 7.5], "side": "both", "allow": ["U5"]},
                               {"name": "hole", "rect_mm": [1.5, 1.5, 4.5, 4.5], "side": "both", "allow": []}]}
    base.update(kw)
    return base


class TestPreflight(unittest.TestCase):
    def setUp(self):
        self.fx = make_board("esp32_4layer")
        self.outline = [{"id": "o1", "layer": 11, "closed": True}]

    def test_fixture_board_with_planes_and_route_keepouts_passes(self):
        rep = run_preflight(SYNTHETIC_DSN, plan_with(), self.fx["dump"], self.outline)
        self.assertTrue(rep.passed, rep.errors)
        self.assertEqual(rep.planes_declared, 2)
        self.assertEqual(rep.planes_in_dsn, 2)
        self.assertEqual(rep.plane_mismatches, [])
        self.assertEqual(rep.outline_primitives, 1)
        self.assertTrue(rep.dsn_boundary_closed)
        self.assertEqual(rep.pads_in_router_keepouts, [])

    def test_pad_inside_a_router_keepout_is_refused(self):
        plan = plan_with(route_keepouts=[{"name": "hole", "rect_mm": [9.0, 31.0, 11.0, 33.0], "side": "both", "allow": []}])
        # U1 (QFN at 10,32 mm in the fixture) has pads inside this keep-out
        rep = run_preflight(SYNTHETIC_DSN, plan, self.fx["dump"], self.outline)
        self.assertFalse(rep.passed)
        self.assertTrue(any("keep-outs" in e for e in rep.errors), rep.errors)
        self.assertTrue(any(h.startswith("U1.") for h in rep.pads_in_router_keepouts), rep.pads_in_router_keepouts[:3])

    def test_missing_or_mismatched_plane_is_refused(self):
        dsn_without_3v3 = SYNTHETIC_DSN.replace(f"(plane 3V3 (polygon Inner2 0 {poly(PLANE_3V3)}))", "")
        rep = run_preflight(dsn_without_3v3, plan_with(), self.fx["dump"], self.outline)
        self.assertFalse(rep.passed)
        self.assertIn("3V3 on Inner2: missing from DSN", rep.plane_mismatches)
        shifted = plan_with(planes=[{"net": "GND", "layer": "Inner1", "polygon_mm": [[0.3, 0.3], [29.7, 0.3], [29.7, 44.7], [1.0, 44.7]]}])
        rep2 = run_preflight(SYNTHETIC_DSN, shifted, self.fx["dump"], self.outline)
        self.assertFalse(rep2.passed)
        self.assertTrue(any("GND on Inner1" in m for m in rep2.plane_mismatches))

    def test_outline_must_be_exactly_one_closed_primitive(self):
        rep = run_preflight(SYNTHETIC_DSN, plan_with(), self.fx["dump"], [{"id": f"l{i}", "layer": 11, "closed": False} for i in range(36)])
        self.assertFalse(rep.passed)
        self.assertEqual(rep.outline_primitives, 36)
        open_dsn = SYNTHETIC_DSN.replace("1181.10 0 0 0))", "1181.10 0))")
        rep2 = run_preflight(open_dsn, plan_with(), self.fx["dump"], self.outline)
        self.assertFalse(rep2.dsn_boundary_closed)
        self.assertFalse(rep2.passed)

    def test_helpers(self):
        planes = dsn_planes(SYNTHETIC_DSN)
        self.assertEqual(set(planes), {("GND", "Inner1"), ("3V3", "Inner2")})
        self.assertEqual(len(planes[("GND", "Inner1")]), 4)
        self.assertTrue(dsn_boundary_closed(SYNTHETIC_DSN))
        hits = pads_inside_keepouts(self.fx["dump"], [{"name": "all", "rect_mm": [-100, -100, 300, 300], "side": "both", "allow": []}])
        self.assertEqual(len(hits), sum(len(c["pads"]) for c in self.fx["dump"].values()))
        allowed = pads_inside_keepouts(self.fx["dump"], [{"name": "ant", "rect_mm": [-100, -100, 300, 300], "side": "both",
                                                          "allow": list(self.fx["dump"].keys())}])
        self.assertEqual(allowed, [])


if __name__ == "__main__":
    unittest.main()
