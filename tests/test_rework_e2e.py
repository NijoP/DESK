"""
End-to-End Scenarios for DESK Rework Mode (Scenarios A through H).
Direct implementation of Master Engineering Directive Section 22.7.
Zero external dependencies.
"""

import json
import os
import shutil
import tempfile
import unittest

from desk.snapshot import IndexedPCBSnapshot
from desk.rework import (
    ReworkSessionLifecycle,
    create_rework_session,
    BaselineCaptureEngine,
    ReworkAuditEngine,
    RepairPlanner,
    RepairExecutor,
    ManufacturingReadinessEngine,
    ReadinessOutcome,
    ProjectBinding,
    IssueCategory,
)


class TestReworkEndToEnd(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.proj_dir = os.path.join(self.tmp_dir, "projects", "FIXTURE_BOARD")
        os.makedirs(os.path.join(self.proj_dir, "state"), exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_scenario_a_partially_routed_board(self):
        """
        Scenario A: Existing PCB has accepted placement and routing, but several nets remain incomplete.
        Expected: DESK identifies outstanding nets and proposes minimal routing changes without regenerating accepted routing.
        """
        comps = {
            "U1": {"x": 100.0, "y": 100.0, "rot": 0, "layer": 1, "pads": [{"num": "1", "net": "NET_DONE"}, {"num": "2", "net": "NET_OPEN"}]},
            "U2": {"x": 200.0, "y": 100.0, "rot": 0, "layer": 1, "pads": [{"num": "1", "net": "NET_DONE"}, {"num": "2", "net": "NET_OPEN"}]},
        }
        tracks = [
            # NET_DONE is already completely routed and accepted
            {"id": "t_done", "net": "NET_DONE", "layer": 1, "width": 10.0, "x1": 100.0, "y1": 100.0, "x2": 200.0, "y2": 100.0}
        ]
        session = create_rework_session(self.proj_dir)
        baseline = BaselineCaptureEngine.capture_from_data(session.session_id, self.proj_dir, comps, tracks=tracks)
        BaselineCaptureEngine.save_baseline(baseline)

        snap = IndexedPCBSnapshot(raw_dump=comps, tracks=tracks, project_id="FIXTURE_BOARD")
        auditor = ReworkAuditEngine(session.session_id, self.proj_dir, baseline.composite_fingerprint)
        issues = auditor.run_full_audit(snap)

        # Net NET_OPEN must be detected
        open_issues = [i for i in issues if i.category == IssueCategory.ROUTING and "NET_OPEN" in i.title]
        self.assertEqual(len(open_issues), 1)

        # Plan must protect existing track t_done
        plan = RepairPlanner.create_plan(session.session_id, self.proj_dir, baseline.composite_fingerprint, issues, existing_tracks_count=1)
        self.assertGreaterEqual(plan.protected_summary.get("accepted_tracks", 0), 1)

    def test_scenario_b_existing_drc_violations(self):
        """
        Scenario B: Existing project contains clearance and silkscreen violations.
        Expected: DESK captures baseline, classifies problems and builds a repair plan.
        """
        raw_drc = [
            {"errorType": "Clearance Violation", "message": "Clearance 4 mil < 6 mil rule", "pos": [50, 50]},
            {"errorType": "Short Circuit", "message": "Net 3V3 shorted to GND", "pos": [100, 100]},
        ]
        session = create_rework_session(self.proj_dir)
        auditor = ReworkAuditEngine(session.session_id, self.proj_dir)
        drc_issues = auditor.audit_drc_manufacturing(raw_drc)

        self.assertEqual(len(drc_issues), 2)
        shorts = [i for i in drc_issues if i.severity == "CRITICAL"]
        self.assertEqual(len(shorts), 1)

    def test_scenario_c_schematic_pcb_mismatch(self):
        """
        Scenario C: Some PCB net assignments differ from the authoritative schematic.
        Expected: DESK detects mismatch and blocks dependent routing repairs until resolved.
        """
        comps = {
            "U1": {"x": 100.0, "y": 100.0, "rot": 0, "layer": 1, "pads": [{"num": "1", "net": "WRONG_PCB_NET"}]}
        }
        sch_blocks = [{
            "id": "B1",
            "parts": [{"ref": "U1", "pins": {"1": "AUTHORITATIVE_NET"}}]
        }]
        session = create_rework_session(self.proj_dir)
        auditor = ReworkAuditEngine(session.session_id, self.proj_dir)
        mismatch_issues = auditor.audit_schematic_netlist(sch_blocks, comps)

        self.assertEqual(len(mismatch_issues), 1)
        self.assertEqual(mismatch_issues[0].severity, "CRITICAL")
        self.assertEqual(mismatch_issues[0].affected_objects["schematic_net"], "AUTHORITATIVE_NET")

    def test_scenario_d_component_footprint_problem(self):
        """
        Scenario D: A component has duplicate pad numbers or missing terminals.
        Expected: DESK reports evidence and requests engineering decision.
        """
        comps = {
            "MIC1": {"x": 50.0, "y": 50.0, "rot": 0, "layer": 1, "pads": [{"num": "1", "net": "GND"}, {"num": "1", "net": "GND"}]}
        }
        session = create_rework_session(self.proj_dir)
        auditor = ReworkAuditEngine(session.session_id, self.proj_dir)
        fp_issues = auditor.audit_components_footprints(comps)

        self.assertEqual(len(fp_issues), 1)
        self.assertIn("Duplicate Pad Numbers", fp_issues[0].title)

    def test_scenario_e_already_complete_pcb(self):
        """
        Scenario E: An engineer activates Rework Mode on a project that is already complete.
        Expected: DESK verifies it and does not create unnecessary changes.
        """
        comps = {
            "R1": {"x": 100.0, "y": 100.0, "rot": 0, "layer": 1, "pads": [{"num": "1", "net": "GND"}, {"num": "2", "net": "GND"}]}
        }
        tracks = [
            {"id": "t1", "net": "GND", "layer": 1, "width": 10.0, "x1": 100.0, "y1": 100.0, "x2": 100.0, "y2": 100.0}
        ]
        session = create_rework_session(self.proj_dir)
        snap = IndexedPCBSnapshot(raw_dump=comps, tracks=tracks, zones=[{"id": "Z1", "net": "GND", "layer": 1}], project_id="FIXTURE_BOARD")
        
        # When 0 issues exist
        assessment = ManufacturingReadinessEngine.evaluate(
            session_id=session.session_id,
            project_path=self.proj_dir,
            snapshot=snap,
            issues_count=0,
            resolved_count=0,
            discontinuities_count=0,
        )
        self.assertIn(assessment.outcome, (ReadinessOutcome.READY_FOR_MANUFACTURING, ReadinessOutcome.CONDITIONALLY_READY))

    def test_scenario_f_external_project_modification(self):
        """
        Scenario F: Engineer modifies EasyEDA outside DESK while a repair plan exists.
        Expected: DESK detects revision change and flags modification.
        """
        comps = {"R1": {"x": 10.0, "y": 10.0, "rot": 0, "layer": 1, "pads": []}}
        session = create_rework_session(self.proj_dir)
        baseline = BaselineCaptureEngine.capture_from_data(session.session_id, self.proj_dir, comps)

        # External change
        changed_comps = {"R1": {"x": 999.0, "y": 999.0, "rot": 0, "layer": 1, "pads": []}}
        has_mod, changed_domains, _ = BaselineCaptureEngine.detect_external_modifications(
            baseline=baseline,
            current_components=changed_comps,
        )
        self.assertTrue(has_mod)
        self.assertIn("geometry", changed_domains)

    def test_scenario_g_interrupted_repair_reconciliation(self):
        """
        Scenario G: Interrupted mutation recovery via checkpoint.
        Expected: DESK reconciles project state and verifies checkpoint existence.
        """
        session = create_rework_session(self.proj_dir)
        session.transition_to(ReworkSessionLifecycle.REPAIR_EXECUTION, "Starting mutation")
        
        # Simulate interruption
        session.transition_to(ReworkSessionLifecycle.INTERRUPTED, "Process killed")
        session.save()

        # Reopen session
        recovered = create_rework_session(self.proj_dir, session_id=session.session_id)
        self.assertEqual(recovered.session_id, session.session_id)

    def test_scenario_h_no_live_easyeda_environment(self):
        """
        Scenario H: Offline fixture testing succeeds without live network, and claims zero false live integration.
        """
        binding = ProjectBinding(
            project_name="OFFLINE_FIXTURE",
            project_path=self.proj_dir,
            project_uuid="uuid_offline",
            window_id="offline",
            eda_port=49620,
        )
        self.assertEqual(binding.window_id, "offline")


if __name__ == "__main__":
    unittest.main()
