import unittest

from desk.routing.dsn_fixture import tiny_board_dsn
from desk.routing.dsn import SExprParser, DSNTree
from desk.routing.preflight import run_preflight, dsn_planes, dsn_boundary_closed


class TestTinyDSN(unittest.TestCase):
    def test_parses_and_has_expected_structure(self):
        txt = tiny_board_dsn(nets=4)
        tree = DSNTree(txt)
        self.assertTrue(tree.find_node(["structure"]))
        self.assertTrue(tree.find_node(["network"]))
        self.assertEqual(txt.count("(net N"), 4)
        self.assertEqual(txt.count("(class N"), 4)
        self.assertTrue(dsn_boundary_closed(txt))
        self.assertIn("(pin psmd ", txt)

    def test_planes_and_keepouts_emitted_and_preflight_passes(self):
        planes = [{"net": "N1", "layer": "Inner1", "polygon_mm": [[1, 1], [19, 1], [19, 19], [1, 19]]}]
        txt = tiny_board_dsn(nets=3, layers=4, planes=planes, keepouts_mil=[("hole", (0, 0, 60, 60))])
        self.assertEqual(set(dsn_planes(txt)), {("N1", "Inner1")})
        rep = run_preflight(txt, {"planes": planes, "route_keepouts": [], "origin_mm": [0, 0]}, {}, [{"id": "o", "layer": 11, "closed": True}])
        self.assertTrue(rep.passed, rep.errors)

    def test_serialises_round_trip(self):
        txt = tiny_board_dsn(nets=2)
        tree = DSNTree(txt)
        out = tree.serialize()
        self.assertIn("(net N1", out)
        self.assertIn("(boundary", out)


if __name__ == "__main__":
    unittest.main()
