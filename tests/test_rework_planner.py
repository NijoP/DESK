"""
Unit tests for DESK Rework Mode Repair Planner, Dependency Analysis & Approval Tokens.
Zero external dependencies.
"""

import os
import shutil
import tempfile
import unittest

from desk.rework import (
    Issue,
    IssueCategory,
    IssueSeverity,
    RepairAction,
    RepairPlan,
    ApprovalToken,
    RepairPlanner,
)


class TestReworkPlanner(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.issues = [
            Issue(
                issue_id="RW-0001",
                session_id="rework_test_plan",
                category=IssueCategory.ROUTING,
                severity=IssueSeverity.HIGH,
                title="Unrouted Net 3V3",
                description="3V3 has 0 tracks",
                affected_objects={"net": "3V3"},
            ),
            Issue(
                issue_id="RW-0002",
                session_id="rework_test_plan",
                category=IssueCategory.SCHEMATIC,
                severity=IssueSeverity.CRITICAL,
                title="Net Mismatch on U1 Pin 1",
                description="Pin 1 net does not match schematic",
                affected_objects={"ref": "U1", "pin": "1"},
            ),
            Issue(
                issue_id="RW-0003",
                session_id="rework_test_plan",
                category=IssueCategory.PLACEMENT,
                severity=IssueSeverity.HIGH,
                title="Component J1 Edge Violation",
                description="J1 is placed outside boundary",
                affected_objects={"ref": "J1"},
            ),
        ]

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_dependency_ordering(self):
        """Validates that repairs are sequenced: Schematic -> Placement -> Routing."""
        plan = RepairPlanner.create_plan(
            session_id="rework_test_plan",
            project_path=self.tmp_dir,
            baseline_revision="rev_base_123",
            issues=self.issues,
            existing_tracks_count=42,
            existing_components_count=10,
        )

        self.assertEqual(len(plan.repairs), 3)
        # Sequence:
        # 1st repair must be SCHEMATIC (RP-0001)
        self.assertEqual(plan.repairs[0].issue_id, "RW-0002")
        self.assertEqual(plan.repairs[0].action_type, "UPDATE_PAD_NET")

        # 2nd repair must be PLACEMENT (RP-0002)
        self.assertEqual(plan.repairs[1].issue_id, "RW-0003")
        self.assertEqual(plan.repairs[1].action_type, "NUDGE_COMPONENT")

        # 3rd repair must be ROUTING (RP-0003), depending on upstream
        self.assertEqual(plan.repairs[2].issue_id, "RW-0001")
        self.assertEqual(plan.repairs[2].action_type, "ROUTE_NET")
        self.assertIn(plan.repairs[0].repair_id, plan.repairs[2].dependencies)

    def test_approval_token_generation_and_persistence(self):
        """Validates that approval tokens are bound to session, repair ID, and revision."""
        plan = RepairPlanner.create_plan(
            session_id="rework_test_plan",
            project_path=self.tmp_dir,
            baseline_revision="rev_base_123",
            issues=self.issues,
        )
        target = plan.repairs[0]
        token = RepairPlanner.generate_approval_token(
            repair=target,
            session_id="rework_test_plan",
            project_id="TEST_PROJ",
            revision_hash="rev_base_123",
            actor="CAPTAIN",
        )

        self.assertTrue(token.token.startswith("RW-APR-"))
        self.assertEqual(token.repair_id, target.repair_id)
        self.assertEqual(token.revision_hash, "rev_base_123")
        self.assertTrue(token.is_valid)

        # Save approval
        RepairPlanner.save_approval(self.tmp_dir, "rework_test_plan", token)
        app_file = os.path.join(self.tmp_dir, "state", "rework", "rework_test_plan", "approvals.json")
        self.assertTrue(os.path.exists(app_file))


if __name__ == "__main__":
    unittest.main()
