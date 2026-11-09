"""Automated Verification Suite for Adaptive Routing Priority Engine.
Tests multidimensional constrainedness scoring, priority stage classification,
and differential pair coordination.
"""
import unittest
from desk.routing.board import BoardIntelligenceEngine
from desk.routing.priority import AdaptivePriorityEngine


class TestRoutingPriority(unittest.TestCase):

    def setUp(self):
        # Create a mock board with differential pair, fine-pitch QFN net, and standard nets
        self.dump = {
            "U1": {
                "x": 300.0, "y": 300.0, "rot": 0, "layer": 1,
                "pads": [
                    # USB Diff Pair
                    {"num": "1", "net": "USB_DP", "dx": -10.0, "dy": 0.0, "w": 8.0, "h": 20.0, "layer": 1},
                    {"num": "2", "net": "USB_DN", "dx": 10.0, "dy": 0.0, "w": 8.0, "h": 20.0, "layer": 1},
                    # High current VBAT
                    {"num": "3", "net": "VBAT", "dx": 30.0, "dy": 0.0, "w": 10.0, "h": 20.0, "layer": 1},
                    # Standard GPIO
                    {"num": "4", "net": "GPIO_1", "dx": 50.0, "dy": 0.0, "w": 10.0, "h": 20.0, "layer": 1},
                ]
            },
            "J1": {
                "x": 800.0, "y": 800.0, "rot": 0, "layer": 1,
                "pads": [
                    {"num": "1", "net": "USB_DP", "dx": 0.0, "dy": 0.0, "w": 20.0, "h": 20.0, "layer": 1},
                    {"num": "2", "net": "USB_DN", "dx": 25.0, "dy": 0.0, "w": 20.0, "h": 20.0, "layer": 1},
                    {"num": "3", "net": "VBAT", "dx": 50.0, "dy": 0.0, "w": 30.0, "h": 30.0, "layer": 1},
                    {"num": "4", "net": "GPIO_1", "dx": 75.0, "dy": 0.0, "w": 20.0, "h": 20.0, "layer": 1},
                ]
            }
        }
        self.board = BoardIntelligenceEngine(1200.0, 1200.0, ["Top", "Inner1", "Inner2", "Bottom"], self.dump)

    def test_adaptive_priority_scoring(self):
        diff_pairs = {"USB": ("USB_DP", "USB_DN")}
        high_current = {"VBAT": 2.0}

        scores = AdaptivePriorityEngine.score_all_nets(
            self.board,
            diff_pairs=diff_pairs,
            high_current=high_current
        )

        score_map = {s.net_name: s for s in scores}
        self.assertIn("USB_DP", score_map)
        self.assertIn("USB_DN", score_map)
        self.assertIn("VBAT", score_map)
        self.assertIn("GPIO_1", score_map)

        # Differential pair legs must receive top criticality
        self.assertEqual(score_map["USB_DP"].criticality_score, 10.0)
        self.assertTrue(score_map["USB_DP"].is_differential_pair)

        # High current power must have high urgency
        self.assertGreater(score_map["VBAT"].constraint_urgency_score, 7.0)

        # Total priority of constrained/critical nets must exceed generic GPIO
        self.assertGreater(score_map["USB_DP"].total_priority, score_map["GPIO_1"].total_priority)


if __name__ == "__main__":
    unittest.main()
