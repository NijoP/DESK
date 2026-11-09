"""Automated Verification Suite for Trace Width, Neckdown, and Post-Routing Widening.
Tests IPC-2152 formula accuracy, QFN pad escape neckdown preservation,
and clearance-verified trunk widening.
"""
import unittest
from desk.routing.width import TraceWidthManager


class TestRoutingWidth(unittest.TestCase):

    def test_ipc2152_width_calculation(self):
        # 1A current on 1 oz copper, 10C delta T
        w_outer = TraceWidthManager.calculate_ipc2152_width(1.0, is_inner=False, copper_oz=1.0)
        # Inner layer requires roughly 2x the copper area
        w_inner = TraceWidthManager.calculate_ipc2152_width(1.0, is_inner=True, copper_oz=1.0)
        self.assertGreater(w_inner, w_outer)

        # 3A current should require substantially wider trace than 0.5A
        w_3a = TraceWidthManager.calculate_ipc2152_width(3.0, is_inner=False)
        w_05a = TraceWidthManager.calculate_ipc2152_width(0.5, is_inner=False)
        self.assertGreater(w_3a, w_05a * 2.0)

    def test_escape_neckdown_preservation_and_cleared_widening(self):
        # Fine-pitch pad at (100, 100), obstacle at (200, 110)
        fine_pitch_pads = [(100.0, 100.0, 10.0)]
        obstacles = [(200.0, 110.0, 250.0, 110.0, 1)]  # Obstacle on Layer 1 close to segment 2

        # Segment 1: Touches fine-pitch pad at (100, 100) -> must keep escape neckdown (10 mil)
        # Segment 2: Open board trunk from (150, 100) to (300, 100) -> constrained by obstacle at Y=110
        # Segment 3: Open board trunk from (400, 100) to (600, 100) -> fully clear, should widen to 30 mil
        segments = [
            {"id": "seg_1", "start_x": 100.0, "start_y": 100.0, "end_x": 130.0, "end_y": 100.0, "width": 10.0, "layer": 1},
            {"id": "seg_2", "start_x": 150.0, "start_y": 100.0, "end_x": 300.0, "end_y": 100.0, "width": 10.0, "layer": 1},
            {"id": "seg_3", "start_x": 400.0, "start_y": 100.0, "end_x": 600.0, "end_y": 100.0, "width": 10.0, "layer": 1},
        ]

        plan = TraceWidthManager.plan_power_widening(
            net_name="VBAT",
            segments=segments,
            target_width_mil=30.0,
            escape_width_mil=10.0,
            fine_pitch_pads=fine_pitch_pads,
            obstacles=obstacles,
            min_clearance_mil=4.02,
            escape_radius_mil=35.0
        )

        self.assertEqual(plan.total_segments, 3)
        self.assertEqual(plan.preserved_escape_segments, 1)

        cands = {c.segment_id: c for c in plan.candidates}
        # Segment 1 must be marked as escape neckdown
        self.assertTrue(cands["seg_1"].is_escape_neckdown)
        self.assertEqual(cands["seg_1"].approved_width_mil, 10.0)

        # Segment 3 must be approved for full 30 mil widening
        self.assertTrue(cands["seg_3"].is_widened)
        self.assertEqual(cands["seg_3"].approved_width_mil, 30.0)


if __name__ == "__main__":
    unittest.main()
