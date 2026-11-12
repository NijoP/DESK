"""DESK Weft nodes against the real deterministic engines, in a temporary project. No bridge, no network.

The tests call nodes in workflow order the way Weft would. They prove the DESK side of the contract (typing,
fail-closed gates, idempotent replay, approvals, trace). Weft's own durable wait and resume are not exercised
here: they need a Weft runtime.
"""
import dataclasses
import json
import os
import shutil
import tempfile
import time
import unittest
from unittest import mock

from desk.weft import contracts as C
from desk.weft import nodes
from desk.weft.store import RecordStore, StoreError

REQ = json.dumps({"text": "12 V input, 5 V 3 A synchronous buck converter module, 500 kHz switching",
                  "voltage_rails": {"VIN": 12.0, "VOUT": 5.0}, "current_limits_A": {"VIN": 1.5, "VOUT": 3.0}})
CLEAN = {"board_revision": "r1", "evidence_revision": "r1", "drc_violations": [], "unconnected_nets": [], "critical_nets": [],
         "routability_score": 1.0, "discontinuities_count": 0}


class NodeCase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="desk_weft_")
        os.makedirs(os.path.join(self.root, "DEMO"))
        self.store = RecordStore("DEMO", self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def call(self, node, run="run-1", provider=None, **inputs):
        return nodes.execute(node, dict(projectId="DEMO", runId=run, **inputs), projects_root=self.root, provider=provider,
                             sleep=lambda s: None)

    def profile(self, requirements=REQ):
        _, e = self.call("DeskRequirementIntake", requirements=requirements)
        h = e["outputs"]["requirementsHash"]
        _, p = self.call("DeskDesignProfileCompiler", requirementsHash=h)
        return h, p["outputs"]["profileHash"]


class RequirementToProfileTests(NodeCase):
    def test_chain_runs_on_real_engines_and_every_output_is_typed(self):
        status, intake = self.call("DeskRequirementIntake", requirements=REQ)
        self.assertEqual(status, 200)
        h = intake["outputs"]["requirementsHash"]
        for node, kw in (("DeskRequirementValidator", {"requirementsHash": h}), ("DeskDomainClassifier", {"requirementsHash": h}),
                         ("DeskDesignProfileCompiler", {"requirementsHash": h})):
            status, env = self.call(node, **kw)
            self.assertEqual(status, 200, env)
            self.assertTrue(env["ok"] and env["passed"], env)
            self.assertEqual(C.get(node).validate_outputs(env["outputs"]), [])
        ph = env["outputs"]["profileHash"]
        _, cls = self.call("DeskDomainClassifier", requirementsHash=h)
        self.assertEqual(cls["outputs"]["primaryArchetype"], "buck_converter")
        _, fam = self.call("DeskComponentFamilyResolver", profileHash=ph)
        self.assertIn("buck_regulator", fam["outputs"]["families"])
        self.assertEqual(fam["outputs"]["unknownFamilies"], [])
        _, power = self.call("DeskPowerDistributionAnalyzer", profileHash=ph)
        self.assertTrue(power["passed"])
        self.assertEqual(power["outputs"]["netCount"], 2)
        from desk import ipc
        self.assertEqual(power["outputs"]["widestTraceMil"], ipc.trace_width_mil(3.0))

    def test_compiled_profile_is_a_desk_record_not_a_workflow_value(self):
        _, ph = self.profile()
        doc = self.store.get_profile(ph)
        self.assertEqual(doc["compiled"]["design_profile"]["profile_hash"], ph)
        self.assertTrue(os.path.exists(os.path.join(self.root, "DEMO", "state", "weft", "profiles", ph + ".json")))

    def test_unclassifiable_requirements_close_the_gate(self):
        _, e = self.call("DeskRequirementIntake", requirements="hello there")
        h = e["outputs"]["requirementsHash"]
        _, cls = self.call("DeskDomainClassifier", requirementsHash=h)
        self.assertTrue(cls["ok"])
        self.assertFalse(cls["passed"])
        self.assertTrue(cls["blockingIssues"])
        _, prof = self.call("DeskDesignProfileCompiler", requirementsHash=h)
        self.assertFalse(prof["passed"])
        self.assertEqual(prof["outputs"]["profileHash"], "")

    def test_unknown_current_is_never_sized(self):
        _, ph = self.profile("12 V input, 5 V 3 A synchronous buck converter module, 500 kHz switching")
        _, power = self.call("DeskPowerDistributionAnalyzer", profileHash=ph)
        self.assertFalse(power["passed"])
        self.assertEqual(power["outputs"]["netCount"], 0)

    def test_empty_requirements_are_blocked_at_intake(self):
        _, e = self.call("DeskRequirementIntake", requirements="   ")
        self.assertFalse(e["passed"])


class ErrorContractTests(NodeCase):
    def test_unknown_node(self):
        status, e = self.call("DeskNoSuchNode")
        self.assertEqual((status, e["error"]["code"]), (404, "UNKNOWN_NODE"))

    def test_invalid_input_is_refused_before_any_engine_runs(self):
        with mock.patch.dict(nodes.HANDLERS, {"DeskDomainClassifier": mock.Mock(side_effect=AssertionError("ran"))}):
            status, e = self.call("DeskDomainClassifier", requirementsHash=5)
        self.assertEqual((status, e["error"]["code"]), (400, "INVALID_INPUT"))
        self.assertFalse(e["ok"])
        self.assertNotIn("outputs", e)

    def test_unknown_project_and_path_escape(self):
        status, e = nodes.execute("DeskRequirementIntake", {"projectId": "NOPE", "runId": "r", "requirements": "x"}, projects_root=self.root)
        self.assertEqual((status, e["error"]["code"]), (404, "PROJECT_NOT_FOUND"))
        for bad in ("../DEMO", "..", "a/b", "C:\\x", ""):
            status, e = nodes.execute("DeskRequirementIntake", {"projectId": bad, "runId": "r", "requirements": "x"}, projects_root=self.root)
            self.assertEqual(e["error"]["code"], "INVALID_INPUT", bad)

    def test_missing_record(self):
        status, e = self.call("DeskDomainClassifier", requirementsHash="0" * 64)
        self.assertEqual((status, e["error"]["code"]), (404, "RECORD_NOT_FOUND"))

    def test_unavailable_node_fails_closed(self):
        for node in ("DeskRoutingExecutor", "DeskSchematicCompiler", "DeskThermalAnalyzer", "DeskBOMGenerator"):
            status, e = self.call(node)
            self.assertEqual((status, e["error"]["code"]), (501, "NODE_UNAVAILABLE"), node)
            self.assertNotIn("passed", e)

    def test_engine_exception_becomes_engine_error(self):
        with mock.patch.dict(nodes.HANDLERS, {"DeskRequirementIntake": mock.Mock(side_effect=RuntimeError("boom"))}):
            status, e = self.call("DeskRequirementIntake", requirements="x")
        self.assertEqual((status, e["error"]["code"]), (500, "ENGINE_ERROR"))
        self.assertFalse(e["error"]["retryable"])

    def test_adapter_that_breaks_its_output_contract_is_an_error_not_a_result(self):
        with mock.patch.dict(nodes.HANDLERS, {"DeskRequirementIntake": lambda ctx, i: ({"requirementsHash": 7}, [], [])}):
            status, e = self.call("DeskRequirementIntake", requirements="x")
        self.assertEqual(e["error"]["code"], "ENGINE_ERROR")
        self.assertIn("contract", e["error"]["message"])

    def test_timeout(self):
        slow = dataclasses.replace(C.get("DeskRequirementIntake"), timeout_s=0.05)
        with mock.patch.dict(C.BY_ID, {"DeskRequirementIntake": slow}), \
                mock.patch.dict(nodes.HANDLERS, {"DeskRequirementIntake": lambda ctx, i: time.sleep(1.0)}):
            status, e = self.call("DeskRequirementIntake", requirements="x")
        self.assertEqual((status, e["error"]["code"]), (504, "TIMEOUT"))
        self.assertTrue(e["error"]["retryable"])


class IdempotencyTests(NodeCase):
    def test_identical_call_replays_the_stored_result_without_running_the_engine(self):
        _, first = self.call("DeskRequirementIntake", requirements=REQ)
        h = first["outputs"]["requirementsHash"]
        _, a = self.call("DeskDomainClassifier", requirementsHash=h)
        self.assertFalse(a["provenance"]["replayed"])
        with mock.patch.dict(nodes.HANDLERS, {"DeskDomainClassifier": mock.Mock(side_effect=AssertionError("engine ran again"))}):
            status, b = self.call("DeskDomainClassifier", run="run-2-after-restart", requirementsHash=h)
        self.assertEqual(status, 200)
        self.assertTrue(b["provenance"]["replayed"])
        self.assertEqual(b["outputs"], a["outputs"])
        self.assertEqual(b["provenance"]["idempotencyKey"], a["provenance"]["idempotencyKey"])

    def test_different_inputs_do_not_share_a_result(self):
        _, a = self.call("DeskRequirementIntake", requirements="5 V 1 A buck converter")
        _, b = self.call("DeskRequirementIntake", requirements="5 V 2 A buck converter")
        self.assertNotEqual(a["provenance"]["idempotencyKey"], b["provenance"]["idempotencyKey"])
        self.assertNotEqual(a["outputs"]["requirementsHash"], b["outputs"]["requirementsHash"])

    def test_failures_are_not_stored(self):
        self.call("DeskDomainClassifier", requirementsHash="0" * 64)
        self.assertFalse(os.path.isdir(os.path.join(self.root, "DEMO", "state", "weft", "results")))


class QualityAndApprovalTests(NodeCase):
    def test_quality_gate_fails_closed_on_missing_evidence_record(self):
        _, ph = self.profile()
        status, e = self.call("DeskQualityGate", profileHash=ph, evidenceRef="none")
        self.assertEqual((status, e["error"]["code"]), (404, "RECORD_NOT_FOUND"))

    def test_quality_gate_does_not_pass_without_drc_and_connectivity_evidence(self):
        _, ph = self.profile()
        self.store.put_evidence("board", {"profile_hash": ph})
        _, e = self.call("DeskQualityGate", profileHash=ph, evidenceRef="board")
        self.assertFalse(e["passed"])
        self.assertFalse(e["outputs"]["approved"])
        self.assertTrue(any("DRC" in f for f in e["outputs"]["failures"]))

    def test_quality_gate_rejects_shorts_and_stale_profile_evidence(self):
        _, ph = self.profile()
        self.store.put_evidence("short", dict(CLEAN, profile_hash=ph, drc_violations=[{"error_type": "Short", "rule_name": "short circuit"}]))
        _, e = self.call("DeskQualityGate", profileHash=ph, evidenceRef="short")
        self.assertFalse(e["passed"])
        self.store.put_evidence("stale", dict(CLEAN, profile_hash="another-profile"))
        _, e = self.call("DeskQualityGate", profileHash=ph, evidenceRef="stale")
        self.assertFalse(e["passed"])

    def test_quality_gate_passes_on_clean_current_evidence(self):
        _, ph = self.profile()
        self.store.put_evidence("clean", dict(CLEAN, profile_hash=ph))
        _, e = self.call("DeskQualityGate", profileHash=ph, evidenceRef="clean")
        self.assertTrue(e["passed"] and e["outputs"]["approved"])

    def test_approval_is_recorded_and_bound_to_its_subject(self):
        _, e = self.call("DeskApprovalRecorder", stage="manufacturing", decision="approved", subjectHash="abc")
        self.assertTrue(e["passed"])
        rec = self.store.get_approval(e["outputs"]["approvalRef"])
        self.assertEqual((rec["stage"], rec["decision"], rec["subject_hash"], rec["run_id"]), ("manufacturing", "approved", "abc", "run-1"))

    def test_rejection_is_recorded_and_closes_the_gate(self):
        _, e = self.call("DeskApprovalRecorder", stage="bom", decision="rejected", subjectHash="abc")
        self.assertTrue(e["ok"])
        self.assertFalse(e["passed"])
        self.assertFalse(e["outputs"]["approved"])

    def test_approval_refuses_unknown_stage_or_decision(self):
        self.assertEqual(self.call("DeskApprovalRecorder", stage="whatever", decision="approved", subjectHash="a")[1]["error"]["code"], "INVALID_INPUT")
        self.assertEqual(self.call("DeskApprovalRecorder", stage="bom", decision="maybe", subjectHash="a")[1]["error"]["code"], "INVALID_INPUT")
        self.assertEqual(self.call("DeskApprovalRecorder", stage="bom", decision="approved", subjectHash="")[1]["error"]["code"], "INVALID_INPUT")

    def test_release_gate_needs_a_real_manufacturing_approval_for_this_profile(self):
        _, ph = self.profile()
        self.store.put_evidence("clean", dict(CLEAN, profile_hash=ph))
        status, e = self.call("DeskReleaseGate", profileHash=ph, evidenceRef="clean", approvalRef="manufacturing-made-up")
        self.assertEqual((status, e["error"]["code"]), (403, "APPROVAL_REQUIRED"))
        _, other = self.call("DeskApprovalRecorder", stage="manufacturing", decision="approved", subjectHash="some-other-profile")
        self.assertEqual(self.call("DeskReleaseGate", profileHash=ph, evidenceRef="clean", approvalRef=other["outputs"]["approvalRef"])[1]["error"]["code"], "APPROVAL_REQUIRED")
        _, bom = self.call("DeskApprovalRecorder", stage="bom", decision="approved", subjectHash=ph)
        self.assertEqual(self.call("DeskReleaseGate", profileHash=ph, evidenceRef="clean", approvalRef=bom["outputs"]["approvalRef"])[1]["error"]["code"], "APPROVAL_REQUIRED")
        _, no = self.call("DeskApprovalRecorder", stage="manufacturing", decision="rejected", subjectHash=ph)
        self.assertEqual(self.call("DeskReleaseGate", profileHash=ph, evidenceRef="clean", approvalRef=no["outputs"]["approvalRef"])[1]["error"]["code"], "APPROVAL_REQUIRED")

    def test_release_gate_allows_release_only_with_approval_and_passing_gates(self):
        _, ph = self.profile()
        _, yes = self.call("DeskApprovalRecorder", stage="manufacturing", decision="approved", subjectHash=ph)
        ref = yes["outputs"]["approvalRef"]
        self.store.put_evidence("bad", {"profile_hash": ph})
        _, e = self.call("DeskReleaseGate", profileHash=ph, evidenceRef="bad", approvalRef=ref)
        self.assertFalse(e["passed"])
        self.assertFalse(e["outputs"]["releaseAllowed"])
        self.store.put_evidence("clean", dict(CLEAN, profile_hash=ph))
        _, e = self.call("DeskReleaseGate", profileHash=ph, evidenceRef="clean", approvalRef=ref)
        self.assertTrue(e["passed"] and e["outputs"]["releaseAllowed"])


class ModelNodeTests(NodeCase):
    GOOD = {"json": {"summary": "5 V 3 A buck", "open_questions": ["ripple target?"], "assumptions": []}, "provider": "fake", "model": "m"}

    def intake(self):
        return self.call("DeskRequirementIntake", requirements=REQ)[1]["outputs"]["requirementsHash"]

    def test_no_provider_is_reported_not_guessed(self):
        status, e = self.call("DeskRequirementExtractor", requirementsHash=self.intake())
        self.assertEqual((status, e["error"]["code"]), (503, "PROVIDER_UNAVAILABLE"))
        self.assertTrue(e["error"]["retryable"])

    def test_model_receives_only_the_instruction_and_the_requirement_text(self):
        seen = []
        h = self.intake()

        def provider(system, user):
            seen.append((system, user))
            return self.GOOD
        _, e = self.call("DeskRequirementExtractor", provider=provider, requirementsHash=h)
        self.assertTrue(e["passed"])
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0][1], REQ)
        self.assertNotIn("DEMO", seen[0][0] + seen[0][1])
        self.assertLess(len(seen[0][0]), 600)

    def test_provider_failure_is_retried_once_then_reported(self):
        h = self.intake()
        calls = []

        def flaky(system, user):
            calls.append(1)
            return {"error": "503 from provider"} if len(calls) == 1 else self.GOOD
        _, e = self.call("DeskRequirementExtractor", provider=flaky, requirementsHash=h)
        self.assertTrue(e["ok"])
        self.assertEqual(e["provenance"]["attempts"], 2)
        dead = mock.Mock(return_value={"error": "down"})
        status, e = self.call("DeskRequirementExtractor", provider=dead, requirementsHash=self.call("DeskRequirementIntake", requirements="3.3 V LDO board")[1]["outputs"]["requirementsHash"])
        self.assertEqual(e["error"]["code"], "PROVIDER_UNAVAILABLE")
        self.assertEqual(dead.call_count, 2)

    def test_malformed_model_output_is_rejected_and_not_retried(self):
        bad = mock.Mock(return_value={"json": {"summary": 5}, "provider": "fake", "model": "m"})
        status, e = self.call("DeskRequirementExtractor", provider=bad, requirementsHash=self.intake())
        self.assertEqual((status, e["error"]["code"]), (502, "PROVIDER_OUTPUT_INVALID"))
        self.assertEqual(bad.call_count, 1)

    def test_model_notes_are_advisory_records_and_do_not_change_classification(self):
        h = self.intake()
        _, before = self.call("DeskDomainClassifier", requirementsHash=h)
        liar = lambda s, u: {"json": {"summary": "this is an RF amplifier", "open_questions": [], "assumptions": ["500 A"]}, "provider": "fake", "model": "m"}
        _, e = self.call("DeskRequirementExtractor", provider=liar, requirementsHash=h)
        with open(os.path.join(self.root, "DEMO", "state", "weft", "notes", e["outputs"]["notesRef"] + ".json"), encoding="utf-8") as f:
            self.assertTrue(json.load(f)["advisory"])
        with mock.patch.object(RecordStore, "get_result", return_value=None):
            _, after = self.call("DeskDomainClassifier", requirementsHash=h)
        self.assertEqual(after["outputs"], before["outputs"])


class TraceTests(NodeCase):
    def test_every_call_is_traced_under_its_weft_run(self):
        h, ph = self.profile()
        self.call("DeskDomainClassifier", requirementsHash="0" * 64)
        self.call("DeskRoutingExecutor")
        trace = self.store.read_trace("run-1")
        self.assertEqual([t["node"] for t in trace], ["DeskRequirementIntake", "DeskDesignProfileCompiler", "DeskDomainClassifier", "DeskRoutingExecutor"])
        self.assertEqual(trace[2]["error"], "RECORD_NOT_FOUND")
        self.assertEqual(trace[3]["error"], "NODE_UNAVAILABLE")
        self.assertIn(f"state/weft/profiles/{ph}.json", trace[1]["evidence"])
        runs = self.store.list_runs()
        self.assertEqual(runs[0]["runId"], "run-1")
        self.assertEqual(runs[0]["failed"], ["DeskDomainClassifier", "DeskRoutingExecutor"])

    def test_trace_holds_hashes_and_references_not_documents(self):
        self.profile()
        with open(os.path.join(self.root, "DEMO", "state", "weft", "runs", "run-1.jsonl"), encoding="utf-8") as f:
            text = f.read()
        self.assertNotIn("synchronous buck", text)

    def test_store_refuses_bad_record_names(self):
        with self.assertRaises(StoreError):
            self.store.get_evidence("../../etc")


if __name__ == "__main__":
    unittest.main()
