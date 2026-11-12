"""Weft node contracts: identity, typing, policies, and the generated Weft node files."""
import os
import unittest

from desk.weft import contracts as C
from desk.weft import nodes, staging, weftgen


class ContractTests(unittest.TestCase):
    def test_contracts_are_well_formed(self):
        self.assertEqual(C.all_problems(), [])

    def test_ids_versions_and_files_are_unique(self):
        ids = [c.node_id for c in C.CONTRACTS]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len({c.weft_file for c in C.CONTRACTS}), len(ids))
        self.assertEqual(C.get("DeskBOMGenerator").weft_file, "bom_generator.weft")
        self.assertEqual(C.get("DeskDomainClassifier").weft_file, "domain_classifier.weft")

    def test_every_available_node_has_a_handler_and_no_unavailable_one_does(self):
        available = {c.node_id for c in C.CONTRACTS if c.status == "available"}
        self.assertEqual(available, set(nodes.HANDLERS))

    def test_unavailable_nodes_say_why(self):
        for c in C.CONTRACTS:
            if c.status == "unavailable":
                self.assertTrue(c.unavailable_reason, c.node_id)
                self.assertIn("NODE_UNAVAILABLE", c.errors)

    def test_mutating_nodes_are_not_available(self):
        for c in C.CONTRACTS:
            if c.mutation:
                self.assertEqual(c.status, "unavailable", c.node_id)

    def test_only_retryable_errors_are_retried(self):
        for c in C.CONTRACTS:
            if c.max_attempts > 1:
                self.assertTrue(C.RETRYABLE & set(c.errors), c.node_id)

    def test_input_validation_reports_missing_wrong_and_unknown(self):
        c = C.get("DeskDomainClassifier")
        self.assertEqual(c.validate_inputs({"projectId": "P", "runId": "r", "requirementsHash": "h"}), [])
        errs = c.validate_inputs({"projectId": 5, "extra": 1})
        self.assertTrue(any("projectId" in e and "string" in e for e in errs))
        self.assertTrue(any("requirementsHash" in e for e in errs))
        self.assertTrue(any("unknown input 'extra'" in e for e in errs))
        self.assertEqual(c.validate_inputs([1]), ["inputs must be a JSON object"])

    def test_boolean_is_not_a_number(self):
        c = C.get("DeskQualityGate")
        self.assertTrue(c.validate_outputs({"approved": True, "totalScore": True, "failures": []}))

    def test_optional_input_may_be_absent(self):
        c = C.get("DeskApprovalRecorder")
        self.assertEqual(c.validate_inputs({"projectId": "P", "runId": "r", "stage": "bom", "decision": "approved", "subjectHash": "h"}), [])

    def test_contract_document_carries_the_policies(self):
        d = C.get("DeskRequirementExtractor").to_dict()
        self.assertEqual(d["policy"]["maxAttempts"], 2)
        self.assertEqual(d["policy"]["retryOn"], ["PROVIDER_UNAVAILABLE", "TIMEOUT"])
        self.assertEqual(C.get("DeskReleaseGate").to_dict()["policy"]["requiresApproval"], "manufacturing")


class GeneratedNodeFileTests(unittest.TestCase):
    def test_committed_node_files_match_the_contracts(self):
        self.assertEqual(weftgen.drift(), [])

    def test_node_file_declares_typed_ports_and_a_node_specific_envelope(self):
        text = weftgen.render(C.get("DeskDesignProfileCompiler"))
        self.assertIn("Group(service: String, projectId: String, runId: String, requirementsHash: String)", text)
        self.assertIn("profileHash: String", text)
        self.assertIn("enforcedRuleCount: Number", text)
        self.assertIn("type DeskDesignProfileCompilerEnvelope = {", text)
        self.assertIn("/v1/nodes/DeskDesignProfileCompiler", text)
        self.assertIn("Cast -> (value: DeskDesignProfileCompilerEnvelope)", text)

    def test_optional_input_is_optional_on_the_request_key_not_the_group_port(self):
        text = weftgen.render(C.get("DeskApprovalRecorder"))
        self.assertIn("note: String)", text)
        self.assertIn("note?: self.note", text)

    def test_no_node_file_carries_a_credential(self):
        for name in os.listdir(weftgen.NODES_DIR):
            with open(os.path.join(weftgen.NODES_DIR, name), encoding="utf-8") as f:
                text = f.read().lower()
            for word in ("bearer ", "authorization:", "api_key", "secret"):
                self.assertNotIn(word, text, name)

    def test_pin_is_a_full_commit_hash(self):
        pin = staging.pin()
        self.assertRegex(pin["commit"], r"^[0-9a-f]{40}$")
        self.assertIn("O'Saasy", pin["license"])


if __name__ == "__main__":
    unittest.main()
