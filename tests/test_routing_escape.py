"""Automated Verification Suite for Real Pad Escape Feasibility Engine.
Tests corridor analysis, pad pitch/gap calculations, QFN fine-pitch constraints,
and escape difficulty classification.
"""
import unittest
from desk.routing.board import BoardIntelligenceEngine
from desk.routing.escape import PadEscapeEngine


class TestRoutingEscape(unittest.TestCase):

    def test_fine_pitch_qfn_escape_classification(self):
        # Model 0.50mm (19.68 mil) pitch QFN pads with 9.84 mil gap
        dump = {
            "U1": {
                "x": 500.0, "y": 500.0, "rot": 0, "layer": 1,
                "pads": [
                    # Pin 12 (adjacent left)
                    {"num": "12", "net": "NET_12", "dx": -19.68, "dy": 0.0, "w": 10.0, "h": 25.0, "layer": 1},
                    # Pin 13 (target VBAT)
                    {"num": "13", "net": "VBAT", "dx": 0.0, "dy": 0.0, "w": 10.0, "h": 25.0, "layer": 1},
                    # Pin 14 (adjacent right)
                    {"num": "14", "net": "NET_14", "dx": 19.68, "dy": 0.0, "w": 10.0, "h": 25.0, "layer": 1},
                ]
            }
        }
        board = BoardIntelligenceEngine(1000.0, 1000.0, ["Top", "Bottom"], dump)
        pad_13 = board.pads["U1.13"]

        analysis = PadEscapeEngine.evaluate_pad_escape(pad_13, board, fine_pitch_clearance_mil=4.02)
        # Pad 13 has neighbors immediately to EAST and WEST at 19.68 mil
        self.assertAlmostEqual(analysis.pitch_mil, 19.68, places=1)
        self.assertIn(analysis.difficulty, ("RESTRICTED_ESCAPE", "CRITICAL_ESCAPE", "MODERATE_ESCAPE"))
        # North and South corridors should be open
        self.assertIn("NORTH", analysis.legal_escape_directions)
        self.assertIn("SOUTH", analysis.legal_escape_directions)
        # East and West should be blocked by pin 12 & 14
        self.assertNotIn("EAST", analysis.legal_escape_directions)
        self.assertNotIn("WEST", analysis.legal_escape_directions)

    def test_isolated_pad_easy_escape(self):
        dump = {
            "J1": {
                "x": 200.0, "y": 200.0, "rot": 0, "layer": 1,
                "pads": [{"num": "1", "net": "SIG_OUT", "dx": 0.0, "dy": 0.0, "w": 40.0, "h": 40.0, "layer": 1}]
            }
        }
        board = BoardIntelligenceEngine(1000.0, 1000.0, ["Top", "Bottom"], dump)
        pad = board.pads["J1.1"]

        analysis = PadEscapeEngine.evaluate_pad_escape(pad, board)
        self.assertEqual(analysis.difficulty, "EASY_ESCAPE")
        self.assertEqual(len(analysis.legal_escape_directions), 8)


if __name__ == "__main__":
    unittest.main()
