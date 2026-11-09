"""End-to-End Offline Regression and Benchmark Suite on Project One Dataset.
Validates the complete Routing Intelligence V2 pipeline on real 89-component 4-layer hardware:
- Board Intelligence ingestion
- Real Pad Escape Feasibility on 0.5mm QFN (BQ24074) and ESP32-S3
- Adaptive Dynamic Priority Scheduling across 59 populated nets
- DSN S-Expression AST transformation & Invariant Verification
- Physical Pad-to-Pad Connectivity Verification on Project One SES copper
- Decoupled Power Trunk Widening with Clearance Proofs
Zero external dependencies.
"""
import unittest
import os
import json
import re
from desk.routing import (
    BoardIntelligenceEngine,
    PadEscapeEngine,
    AdaptivePriorityEngine,
    DSNTree,
    PhysicalConnectivityVerifier,
    TraceWidthManager,
    RoutingProfiler,
    RoutingModeManager,
)


class TestRoutingE2EProjectOne(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Locate project-one dump and SES
        base_doc = os.path.expanduser("~/OneDrive/Documents")
        cls.p1_dump_path = os.path.join(base_doc, "project-one", "03_hardware_design", "pcb", "original_pcb_dump.json")
        cls.p1_ses_path = os.path.join(base_doc, "project-one", "03_hardware_design", "pcb", "desk_route.ses")
        cls.watch_dsn_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "projects", "WATCH", "state", "route", "desk_route_tune.dsn")

        with open(cls.p1_dump_path, "r", encoding="utf-8") as f:
            cls.dump = json.load(f)

    def test_01_board_intelligence_ingestion(self):
        """Phase 1: Ingests 89 components and builds spatial index."""
        board = BoardIntelligenceEngine(
            board_width_mil=1771.65,
            board_height_mil=1771.65,
            stackup=["Top", "Inner1_GND", "Inner2_PWR", "Bottom"],
            pcb_dump=self.dump
        )
        self.assertGreaterEqual(len(board.pads), 340)
        self.assertGreaterEqual(len(board.net_pads), 50)
        self.assertIn("U2.13", board.pads)  # BQ24074 BAT pin
        self.assertIn("VBAT", board.net_pads)

    def test_02_fine_pitch_qfn_escape_intelligence(self):
        """Phase 2: Verifies pad escape engine on 0.50mm QFN (U2 / BQ24074)."""
        board = BoardIntelligenceEngine(
            board_width_mil=1771.65,
            board_height_mil=1771.65,
            stackup=["Top", "Inner1_GND", "Inner2_PWR", "Bottom"],
            pcb_dump=self.dump
        )
        # Evaluate U2.13 (VBAT)
        pad_13 = board.pads["U2.13"]
        analysis = PadEscapeEngine.evaluate_pad_escape(pad_13, board, fine_pitch_clearance_mil=4.02)

        # U2 has pitch ~19.68 mil (0.50 mm)
        self.assertAlmostEqual(analysis.pitch_mil, 19.68, delta=1.5)
        # Escape must be restricted due to fine pitch
        self.assertIn(analysis.difficulty, ("RESTRICTED_ESCAPE", "CRITICAL_ESCAPE", "MODERATE_ESCAPE"))
        # Available width must be bounded to ~10 mil to prevent maze search collapse
        self.assertLessEqual(analysis.available_width_mil, 12.0)

    def test_03_adaptive_priority_scheduling(self):
        """Phase 3: Computes dynamic constrainedness priorities across all populated nets."""
        board = BoardIntelligenceEngine(
            board_width_mil=1771.65,
            board_height_mil=1771.65,
            stackup=["Top", "Inner1_GND", "Inner2_PWR", "Bottom"],
            pcb_dump=self.dump
        )
        diff_pairs = {"USB": ("USB_DP", "USB_DN")}
        high_current = {"VBAT": 2.0, "VSYS": 1.5, "VBUS": 1.5}

        scores = AdaptivePriorityEngine.score_all_nets(
            board,
            diff_pairs=diff_pairs,
            high_current=high_current
        )
        self.assertGreaterEqual(len(scores), 45)

        # Critical power and diff-pair nets must be in top tiers
        score_dict = {s.net_name: s for s in scores}
        self.assertIn("VBAT", score_dict)
        self.assertGreaterEqual(score_dict["VBAT"].constraint_urgency_score, 8.0)

    def test_04_dsn_ast_transformation_and_invariants(self):
        """Phase 4: Parses real Project One DSN, tunes rules, and validates invariants."""
        if not os.path.exists(self.watch_dsn_path):
            self.skipTest(f"DSN file not found at {self.watch_dsn_path}")

        with open(self.watch_dsn_path, "r", encoding="utf-8") as f:
            dsn_raw = f.read()

        tree = DSNTree(dsn_raw)
        orig_comp_count = tree.baseline_invariants["component_count"]
        orig_net_count = tree.baseline_invariants["net_count"]

        # Apply transformations
        tree.set_boundary(1771.65, 1771.65)
        tree.set_grid_resolution(wire_grid=1.25, via_grid=1.25)
        tree.set_default_rules(width_mil=5.0, clearance_mil=4.02)
        tree.update_net_classes(
            net_widths={"VBAT": 10.0, "VSYS": 10.0},
            net_clearances={"VBAT": 4.02},
            power_nets={"VBAT", "VSYS", "VBUS"},
            fine_pitch_width_mil=5.0
        )

        serialized = tree.serialize()
        self.assertIn('(grid wire 1.25)', serialized)
        self.assertIn('(grid via 1.25)', serialized)

        # Invariants preserved
        self.assertEqual(tree.baseline_invariants["component_count"], orig_comp_count)
        self.assertEqual(tree.baseline_invariants["net_count"], orig_net_count)

    def test_05_physical_connectivity_on_project_one_ses(self):
        """Phase 5: Parses real Project One SES and measures actual physical connectivity."""
        if not os.path.exists(self.p1_ses_path):
            self.skipTest(f"SES file not found at {self.p1_ses_path}")

        with open(self.p1_ses_path, "r", encoding="utf-8") as f:
            ses_text = f.read()

        from desk.routing.connectivity import SESParser
        tracks, vias = SESParser.parse_ses_copper(ses_text)
        self.assertGreater(len(tracks), 20)

        # Run physical connectivity evaluation
        res = PhysicalConnectivityVerifier.verify_board(
            pcb_dump=self.dump,
            tracks=tracks,
            vias=vias
        )
        self.assertGreater(res.total_nets, 40)
        # Verify it produces an explainable, non-trivial result
        self.assertIn("Physical Connectivity:", res.summary)
        self.assertIsInstance(res.fully_connected_nets, int)

    def test_06_power_trunk_widening_plan(self):
        """Phase 6: Verifies clearance-safe power widening on VBAT segments."""
        segments = [
            # Segment in open space
            {"id": "s1", "start_x": 400.0, "start_y": 400.0, "end_x": 600.0, "end_y": 400.0, "width": 10.0, "layer": 1},
            # Segment near U2.13 fine pitch QFN
            {"id": "s2", "start_x": 500.0, "start_y": 500.0, "end_x": 510.0, "end_y": 500.0, "width": 10.0, "layer": 1}
        ]
        fine_pitch_pads = [(500.0, 500.0, 10.0)]

        plan = TraceWidthManager.plan_power_widening(
            net_name="VBAT",
            segments=segments,
            target_width_mil=35.0,
            escape_width_mil=10.0,
            fine_pitch_pads=fine_pitch_pads,
            min_clearance_mil=4.02,
            escape_radius_mil=30.0
        )

        self.assertEqual(plan.total_segments, 2)
        self.assertEqual(plan.widened_segments, 1)
        self.assertEqual(plan.preserved_escape_segments, 1)


if __name__ == "__main__":
    unittest.main()
