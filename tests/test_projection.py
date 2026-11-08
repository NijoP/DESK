"""
Unit tests for DESK ExecutionProjection and stage state machine.
"""

import os
import shutil
import tempfile
import time
import unittest

from desk.runtime.events import EventBus
from desk.runtime.projection import (
    CANONICAL_STAGES,
    STAGE_PCB_ROUTING,
    STAGE_REQUIREMENT_INGESTION,
    ExecutionProjection,
    redact_sensitive,
)


class TestExecutionProjection(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.project_path = os.path.join(self.temp_dir, "test_proj")
        os.makedirs(os.path.join(self.project_path, "state"), exist_ok=True)
        self.bus = EventBus()
        self.projection = ExecutionProjection(project_id=self.project_path, event_bus=self.bus)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_canonical_12_stages_initialized(self):
        summary = self.projection.get_summary()
        self.assertEqual(len(summary["stages"]), 12)
        for s in CANONICAL_STAGES:
            self.assertIn(s, summary["stages"])
            self.assertEqual(summary["stages"][s]["status"], "PENDING")

    def test_stage_lifecycle_events(self):
        # 1. Start requirement ingestion
        self.bus.emit("stage.start", stage=STAGE_REQUIREMENT_INGESTION, message="Reading REQUIREMENTS.md")
        self.assertEqual(self.projection.status, "RUNNING")
        self.assertEqual(self.projection.current_stage, STAGE_REQUIREMENT_INGESTION)
        self.assertEqual(self.projection.stages[STAGE_REQUIREMENT_INGESTION].status, "RUNNING")

        # 2. Progress
        self.bus.emit("stage.progress", stage=STAGE_REQUIREMENT_INGESTION, progress=50.0, message="Power tree verified")
        self.assertEqual(self.projection.stages[STAGE_REQUIREMENT_INGESTION].progress, 50.0)

        # 3. Complete
        self.bus.emit("stage.complete", stage=STAGE_REQUIREMENT_INGESTION, message="Gate R PASSED")
        self.assertEqual(self.projection.stages[STAGE_REQUIREMENT_INGESTION].status, "COMPLETED")
        self.assertEqual(self.projection.stages[STAGE_REQUIREMENT_INGESTION].progress, 100.0)

        # Overall progress should reflect Stage 1 (weight = 5.0)
        self.assertAlmostEqual(self.projection.calculate_overall_progress(), 5.0, delta=0.5)

    def test_progress_never_100_prematurely(self):
        # Complete stage 1 to 11
        for s in CANONICAL_STAGES[:-1]:
            self.bus.emit("stage.start", stage=s)
            self.bus.emit("stage.complete", stage=s)

        prog = self.projection.calculate_overall_progress()
        self.assertLess(prog, 100.0)
        self.assertNotEqual(self.projection.status, "COMPLETED")

        # Complete final stage 12
        final_stage = CANONICAL_STAGES[-1]
        self.bus.emit("stage.start", stage=final_stage)
        self.bus.emit("stage.complete", stage=final_stage)

        self.assertEqual(self.projection.calculate_overall_progress(), 100.0)
        self.assertEqual(self.projection.status, "COMPLETED")

    def test_stage_failure_sets_blocked(self):
        self.bus.emit("stage.start", stage=STAGE_PCB_ROUTING)
        self.bus.emit("stage.fail", stage=STAGE_PCB_ROUTING, error="Freerouting clearance collision on net GND")

        self.assertEqual(self.projection.status, "FAILED")
        self.assertEqual(self.projection.stages[STAGE_PCB_ROUTING].status, "FAILED")
        self.assertIn("collision", self.projection.stages[STAGE_PCB_ROUTING].errors[0])
        self.assertEqual(self.projection.engineering_results["final_acceptance_state"], "BLOCKED")

    def test_redact_sensitive_credentials(self):
        raw = "Connecting to api_key=sk-ant-api03-abcdef12345678901234567890 with bearer ghp_1234567890abcdef1234567890"
        redacted = redact_sensitive(raw)
        self.assertNotIn("sk-ant", redacted)
        self.assertNotIn("ghp_", redacted)
        self.assertIn("[REDACTED]", redacted)

    def test_restart_reconciliation_marks_interrupted(self):
        # Simulate an execution that was running under another PID
        self.bus.emit("stage.start", stage=STAGE_PCB_ROUTING, message="Running pass 12")
        self.projection.persist_state()

        # Modify persisted file to fake an old PID
        state_file = self.projection._state_file_path()
        import json
        with open(state_file, "r") as f:
            data = json.load(f)
        data["pid"] = 99999999  # Non-existent or old PID
        with open(state_file, "w") as f:
            json.dump(data, f)

        # Create new projection instance (simulating DESK restart)
        new_proj = ExecutionProjection(project_id=self.project_path, event_bus=EventBus())
        self.assertEqual(new_proj.status, "INTERRUPTED")
        self.assertEqual(new_proj.stages[STAGE_PCB_ROUTING].status, "INTERRUPTED")
        self.assertEqual(new_proj.engineering_results["evidence_status"], "STALE")


if __name__ == "__main__":
    unittest.main()
