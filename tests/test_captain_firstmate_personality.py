"""
Unit tests for the Captain-FirstMate Personality and Ship Bridge Protocol.
"""

import unittest

from desk.ship import MissionType, ShipBridge


class TestCaptainFirstMatePersonality(unittest.TestCase):
    def test_greeting_detection(self):
        # Pure greetings
        self.assertTrue(ShipBridge.is_simple_greeting("Hello"))
        self.assertTrue(ShipBridge.is_simple_greeting("Good morning"))
        self.assertTrue(ShipBridge.is_simple_greeting("Hey"))
        self.assertTrue(ShipBridge.is_simple_greeting("Hi there"))

        # Engineering commands containing greeting-like words must NOT be simple greetings
        self.assertFalse(ShipBridge.is_simple_greeting("Hello, please route the power stage net VIN"))
        self.assertFalse(ShipBridge.is_simple_greeting("Hey check DRC clearance on U1"))
        self.assertFalse(ShipBridge.is_simple_greeting("pour copper zone on layer 1"))

    def test_mission_classification(self):
        # Greetings
        self.assertEqual(ShipBridge.classify_mission("Good day"), MissionType.GREETING)

        # Ship tasks (mutating)
        self.assertEqual(
            ShipBridge.classify_mission("Route trace for RF antenna 50 ohm"),
            MissionType.SHIP_TASK,
        )
        self.assertEqual(
            ShipBridge.classify_mission("Pour copper plane for ground"),
            MissionType.SHIP_TASK,
        )
        self.assertEqual(
            ShipBridge.classify_mission("Place decoupling capacitors C1 and C2"),
            MissionType.SHIP_TASK,
        )

        # Scout tasks (read-only investigations)
        self.assertEqual(
            ShipBridge.classify_mission("Audit ground plane return paths"),
            MissionType.SCOUT_TASK,
        )
        self.assertEqual(
            ShipBridge.classify_mission("Check DRC clearance violations"),
            MissionType.SCOUT_TASK,
        )
        self.assertEqual(
            ShipBridge.classify_mission("Calculate trace width for 5A current"),
            MissionType.SCOUT_TASK,
        )

        # Bridge controls
        self.assertEqual(ShipBridge.classify_mission("All stop!"), MissionType.BRIDGE_CONTROL)
        self.assertEqual(ShipBridge.classify_mission("Emergency stop immediately"), MissionType.BRIDGE_CONTROL)

    def test_format_greeting_response(self):
        resp = ShipBridge.format_greeting_response()
        self.assertIn("Captain", resp)
        self.assertIn("First Mate", resp)
        self.assertIn("bridge", resp.lower())

    def test_captain_approval_thresholds(self):
        # Destructive deletions require approval
        req_del, reason_del = ShipBridge.requires_captain_approval("clear_block_layout")
        self.assertTrue(req_del)
        self.assertIn("destructive", reason_del.lower())

        # Manufacturing release requires approval
        req_rel, reason_rel = ShipBridge.requires_captain_approval("generate_gerber_release")
        self.assertTrue(req_rel)
        self.assertIn("manufacturing", reason_rel.lower())

        # Safe read operations do not require approval
        req_read, _ = ShipBridge.requires_captain_approval("verify_clearance")
        self.assertFalse(req_read)


if __name__ == "__main__":
    unittest.main()
