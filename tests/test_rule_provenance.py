"""Evidence states, transitions and reference traceability for every rule in the library."""
import unittest

from desk import ipc
from desk.domain_intelligence import get_library
from desk.domain_intelligence.provenance import check_rule, can_transition, rule_provenance, EXECUTABLE_STATES


class ProvenanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lib = get_library()
        cls.refs = cls.lib.references()

    def test_every_rule_is_traceable(self):
        problems = []
        for r in self.lib.rules().values():
            problems += check_rule(r, self.refs, standards_verified=bool(ipc.verified_against_standard))
        self.assertEqual(problems, [], "\n".join(problems))

    def test_enforced_rules_have_executable_evidence(self):
        for r in self.lib.rules().values():
            if r.mode == "ENFORCED":
                self.assertIn(r.status, EXECUTABLE_STATES, r.rule_id)
                self.assertNotEqual(r.evaluation_method, "advisory", r.rule_id)

    def test_no_rule_claims_verification_against_source_yet(self):
        # ipc.verified_against_standard is False: nothing in the library may claim more than OFFLINE_TESTED
        for r in self.lib.rules().values():
            self.assertNotIn(r.status, ("VERIFIED_AGAINST_SOURCE", "LIVE_VERIFIED"), r.rule_id)

    def test_blocking_rules_cite_a_source(self):
        for r in self.lib.rules().values():
            if r.severity == "BLOCKING":
                self.assertTrue(r.source_references, r.rule_id)

    def test_transitions(self):
        self.assertTrue(can_transition("DRAFT", "IMPLEMENTED"))
        self.assertTrue(can_transition("IMPLEMENTED", "OFFLINE_TESTED"))
        self.assertFalse(can_transition("OFFLINE_TESTED", "VERIFIED_AGAINST_SOURCE"))
        self.assertTrue(can_transition("OFFLINE_TESTED", "VERIFIED_AGAINST_SOURCE", human_approved=True))
        self.assertFalse(can_transition("DRAFT", "LIVE_VERIFIED", human_approved=True))
        self.assertTrue(can_transition("BLOCKED", "DRAFT"))

    def test_provenance_record(self):
        p = rule_provenance(self.lib.rule("ELEC-CLEAR-003"), self.refs)
        self.assertEqual(p["status"], "OFFLINE_TESTED")
        self.assertTrue(any(ref["id"] == "IPC-2221B" for ref in p["references"]))
        self.assertIn("Table 6-1", p["references"][0]["clause_notes"])

    def test_unknown_reference_is_reported(self):
        r = self.lib.rule("ELEC-WIDTH-001")
        r2 = type(r).from_dict(dict(r.to_dict(), source_references=["NOT-A-STANDARD"]))
        self.assertTrue(any("NOT-A-STANDARD" in p for p in check_rule(r2, self.refs)))


if __name__ == "__main__":
    unittest.main()
