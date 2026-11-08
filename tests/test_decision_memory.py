"""Unit tests for Phase 9: Structured Decision Memory and Invalidation.
"""
import unittest
import os
import tempfile
from desk import ledger as LG

class TestDecisionMemory(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.proj = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_01_record_and_query_decision(self):
        # Add structured decision memory
        rec = LG.add_decision_record(
            project=self.proj,
            decision="Select TPS62840 for ultra-low quiescent current",
            source="Datasheet p.12",
            model_id="M1_SCHEMATIC",
            model_version="1.0.0",
            req_ids=["R-03", "R-05"],
            alternatives=["MAX38640", "AP61300"],
            reasoning="60nA Iq required for 5-year battery life budget",
            profile_hash="hash_v1"
        )
        self.assertEqual(rec["type"], "decision")
        self.assertEqual(rec["model_id"], "M1_SCHEMATIC")
        self.assertIn("R-03", rec["req_ids"])

        # Query by requirement ID
        matches = LG.query_decision_memory(self.proj, req_id="R-03", current_profile_hash="hash_v1")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["staleness"], "FRESH")

        # Query with changed profile hash -> must flag as STALE
        stale_matches = LG.query_decision_memory(self.proj, req_id="R-03", current_profile_hash="hash_v2_changed")
        self.assertEqual(len(stale_matches), 1)
        self.assertEqual(stale_matches[0]["staleness"], "STALE")

if __name__ == "__main__":
    unittest.main()
