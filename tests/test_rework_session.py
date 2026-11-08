"""
Unit tests for DESK Rework Mode Session Lifecycle, Intent Detection, and Persistence.
Zero external dependencies.
"""

import os
import shutil
import tempfile
import time
import unittest

from desk.rework import (
    DESK_MODE_DESIGN,
    DESK_MODE_REWORK,
    DESK_MODE_AUDIT,
    detect_mode_intent,
    is_rework_intent,
    ReworkSession,
    ReworkSessionLifecycle,
    ReworkExecutionPolicy,
    create_rework_session,
    load_rework_session,
    get_latest_rework_session,
)


class TestReworkSession(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_natural_language_intent_detection(self):
        """Validates that conversational triggers activate Rework Mode."""
        prompts_rework = [
            "Activate Rework Mode.",
            "I want to rework an existing PCB.",
            "Continue my unfinished EasyEDA project.",
            "Take this PCB to manufacturing readiness.",
            "Audit this existing project and tell me what remains.",
            "rework this board",
            "Please repair existing PCB",
        ]
        for p in prompts_rework:
            mode, conf = detect_mode_intent(p)
            self.assertEqual(mode, DESK_MODE_REWORK, f"Failed on: {p}")
            self.assertGreaterEqual(conf, 0.80)
            self.assertTrue(is_rework_intent(p))

    def test_audit_only_intent_detection(self):
        """Validates explicit read-only audit intent."""
        prompts_audit = [
            "Activate audit mode",
            "Audit only",
            "Read-only inspection of this pcb",
        ]
        for p in prompts_audit:
            mode, conf = detect_mode_intent(p)
            self.assertEqual(mode, DESK_MODE_AUDIT)
            self.assertTrue(is_rework_intent(p))

    def test_new_design_intent_does_not_activate_rework(self):
        """Validates that new project creation stays in Design Mode."""
        prompts_new = [
            "Start a new project",
            "Create a new PCB from scratch",
            "Design a new board for a sensor",
        ]
        for p in prompts_new:
            mode, conf = detect_mode_intent(p)
            self.assertEqual(mode, DESK_MODE_DESIGN)
            self.assertFalse(is_rework_intent(p))

    def test_session_creation_and_persistence(self):
        """Validates session state machine, atomic disk save, and reloading."""
        session = create_rework_session(self.tmp_dir, policy="AUDIT_ONLY")
        self.assertTrue(session.session_id.startswith("rework_"))
        self.assertEqual(session.state, ReworkSessionLifecycle.REWORK_REQUESTED.value)

        # Transition state
        session.transition_to(ReworkSessionLifecycle.BASELINE_CAPTURE, "Baseline captured")
        self.assertEqual(session.state, ReworkSessionLifecycle.BASELINE_CAPTURE.value)
        self.assertEqual(len(session.history), 1)

        # Reload from disk
        loaded = load_rework_session(self.tmp_dir, session.session_id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.session_id, session.session_id)
        self.assertEqual(loaded.state, ReworkSessionLifecycle.BASELINE_CAPTURE.value)
        self.assertEqual(loaded.policy, "AUDIT_ONLY")

    def test_latest_session_discovery(self):
        """Validates that get_latest_rework_session discovers the most recently modified session."""
        s1 = create_rework_session(self.tmp_dir, session_id="rework_1001_aaa")
        time.sleep(0.05)
        s2 = create_rework_session(self.tmp_dir, session_id="rework_1002_bbb")

        latest = get_latest_rework_session(self.tmp_dir)
        self.assertIsNotNone(latest)
        self.assertEqual(latest.session_id, s2.session_id)


if __name__ == "__main__":
    unittest.main()
