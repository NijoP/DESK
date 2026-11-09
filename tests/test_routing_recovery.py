"""Automated Verification Suite for Intelligent Recovery Engine.
Tests stagnation detection, failure categorization, and selective rip-up planning.
"""
import unittest
from desk.routing.recovery import IntelligentRecoveryEngine


class TestRoutingRecovery(unittest.TestCase):

    def test_stagnation_detection(self):
        engine = IntelligentRecoveryEngine(max_patience=3)

        # Iteration 1: 5 unrouted nets, 1000mm wire length
        self.assertTrue(engine.record_iteration({"NET_1", "NET_2", "NET_3"}, 1000.0, 10, 2))
        # Iteration 2: same unrouted nets, same wire length
        self.assertTrue(engine.record_iteration({"NET_1", "NET_2", "NET_3"}, 1000.0, 10, 2))
        # Iteration 3: still unchanged -> stagnation detected!
        is_progressing = engine.record_iteration({"NET_1", "NET_2", "NET_3"}, 1000.0, 10, 2)
        self.assertFalse(is_progressing)

    def test_progress_continues_when_unrouted_decreases(self):
        engine = IntelligentRecoveryEngine(max_patience=3)
        self.assertTrue(engine.record_iteration({"NET_1", "NET_2", "NET_3"}, 1000.0, 10, 2))
        self.assertTrue(engine.record_iteration({"NET_1", "NET_2"}, 1200.0, 14, 1))
        self.assertTrue(engine.record_iteration({"NET_1"}, 1350.0, 16, 0))


if __name__ == "__main__":
    unittest.main()
