import unittest

from desk.placement import plan_board_sync, MIL
from desk.routing.fixtures import make_board


class TestPlanBoardSync(unittest.TestCase):
    def setUp(self):
        self.fx = make_board("mcu_2layer_compact")
        self.plan = {"origin_mm": [0.0, 0.0],
                     "parts": [[r, c["x"] / MIL, c["y"] / MIL, c.get("rot") or 0, "T" if c.get("layer", 1) == 1 else "B", "fixture"]
                               for r, c in self.fx["dump"].items()]}

    def test_in_sync_board_has_no_errors(self):
        errs, m = plan_board_sync(self.fx["dump"], self.plan)
        self.assertEqual(errs, [])
        self.assertEqual(m["parts_checked"], len(self.fx["dump"]))

    def test_moved_rotated_and_missing_parts_are_reported(self):
        plan = {"origin_mm": [0.0, 0.0], "parts": [list(p) for p in self.plan["parts"]]}
        plan["parts"][0][1] += 1.0          # moved 1 mm
        plan["parts"][1][3] = (plan["parts"][1][3] + 90) % 360
        plan["parts"].append(["R999", 1, 1, 0, "T", "ghost"])
        errs, m = plan_board_sync(self.fx["dump"], plan)
        self.assertTrue(any("off by" in e for e in errs))
        self.assertTrue(any("rotation" in e for e in errs))
        self.assertTrue(any("not on the board" in e for e in errs))
        self.assertEqual(m["parts_missing"], 1)


if __name__ == "__main__":
    unittest.main()
