"""Tests for Hardened Routing Engine, Convergence Tracking, and Readback Verification."""

import unittest
from desk.router import (
    RoutingPriorityScheduler,
    DSNTuningEngine,
    RoutingConvergenceController,
    verify_routing_result,
    RoutingPlan,
    RoutingConstraint,
)
from desk.models import NetEndpoint, NetConnectivityGraph
from desk.profile import DesignProfile, RFProfile, DiffPairProfile, ManufacturerProfile
from desk.router import RoutingPlanGenerator


class TestRouterHardening(unittest.TestCase):
    def test_profile_precedence_over_regex_heuristics(self):
        # A net named 'GENERIC_NET_99' with RF profile must go to Stage 3 (Critical)
        profile = DesignProfile(
            project_id="P_ROUTER",
            rf_lines={"GENERIC_NET_99": RFProfile(net="GENERIC_NET_99")},
        )
        endpoints = {
            "GENERIC_NET_99": [
                NetEndpoint("U1", "1", "GENERIC_NET_99", 0.0, 0.0, 1),
                NetEndpoint("U2", "2", "GENERIC_NET_99", 10.0, 10.0, 1),
            ],
            "NORMAL_SIGNAL": [
                NetEndpoint("U1", "3", "NORMAL_SIGNAL", 0.0, 0.0, 1),
                NetEndpoint("U2", "4", "NORMAL_SIGNAL", 10.0, 10.0, 1),
            ],
        }
        stages = RoutingPriorityScheduler.schedule_nets(
            endpoints, profile=profile
        )
        self.assertIn("GENERIC_NET_99", stages[3])
        self.assertIn("NORMAL_SIGNAL", stages[6])

    def test_dsn_tuning_per_net_widths(self):
        sample_dsn = """
(boundary (path signal 0 0 0 0 100 100 100 100 0 0 0))
(rule (width 5.0))
(class PWR 'VIN' (rule (width 5.0) (clearance 4.02)))
(class SIG 'DATA' (rule (width 5.0) (clearance 4.02)))
"""
        tuned = DSNTuningEngine.tune_dsn(
            sample_dsn,
            board_outline_mil=(2000.0, 2000.0),
            net_widths={"PWR": 35.0},
            net_clearances={"PWR": 8.0},
        )
        # Verify PWR has width 35.0 and clearance 8.0
        self.assertIn("(width 35.0)", tuned)
        self.assertIn("(clearance 8.0)", tuned)

    def test_routing_convergence_controller(self):
        controller = RoutingConvergenceController(max_attempts=4)
        
        # Attempts 1, 2, 3 with identical unrouted set
        unrouted = {"NET_A", "NET_B"}
        cont1 = controller.record_attempt(unrouted)
        self.assertTrue(cont1)
        cont2 = controller.record_attempt(unrouted)
        self.assertTrue(cont2)
        
        # 3rd consecutive identical unrouted set terminates loop!
        cont3 = controller.record_attempt(unrouted)
        self.assertFalse(cont3)
        self.assertEqual(sorted(controller.get_stalled_nets()), ["NET_A", "NET_B"])

    def test_routing_readback_verification(self):
        plan = RoutingPlan(
            board_stackup=["Top", "Bottom"],
            stage_nets={6: ["NET_1", "NET_2"]},
            net_constraints={
                "NET_1": RoutingConstraint(net="NET_1", min_width_mil=6.0, clearance_mil=5.0),
                "NET_2": RoutingConstraint(net="NET_2", min_width_mil=6.0, clearance_mil=5.0),
            }
        )
        readback_tracks = [
            {"net": "NET_1", "layer": 1, "width": 0.15},
        ]
        res = verify_routing_result(plan, readback_tracks)
        self.assertFalse(res["is_complete"])
        self.assertEqual(res["routed_net_count"], 1)
        self.assertEqual(res["missing_nets"], ["NET_2"])
        self.assertEqual(res["coverage_pct"], 50.0)


class TestPlanFailsClosedWithoutProfile(unittest.TestCase):
    """F-02: no literal clearances or assumed currents; every heuristic is recorded and the plan is blocked."""

    def _graph(self):
        return NetConnectivityGraph(nets={
            "VBUS": [NetEndpoint("U1", "1", "VBUS", 0.0, 0.0, 1), NetEndpoint("C1", "1", "VBUS", 5.0, 0.0, 1)],
            "DATA": [NetEndpoint("U1", "2", "DATA", 0.0, 1.0, 1), NetEndpoint("U2", "2", "DATA", 5.0, 1.0, 1)],
        })

    def test_no_profile_blocks_plan_and_records_assumptions(self):
        plan = RoutingPlanGenerator.generate_plan(self._graph(), {}, (50.0, 50.0), rules={"power_nets": ["VBUS"]})
        self.assertTrue(plan.blocking_issues and plan.blocking_issues[0].startswith("PROFILE:"))
        fab_min = ManufacturerProfile().min_clearance_mil
        for c in plan.net_constraints.values():
            self.assertEqual(c.clearance_mil, fab_min)
        self.assertTrue(any(a.startswith("VBUS:") and "ASSUMED" in a for a in plan.assumptions), plan.assumptions)

    def test_profile_drives_every_number(self):
        profile = DesignProfile(project_id="P_PLAN", voltage_rails={"VBUS": 5.0}, current_limits_A={"VBUS": 1.5})
        plan = RoutingPlanGenerator.generate_plan(self._graph(), {}, (50.0, 50.0), rules={"power_nets": ["VBUS"]},
                                                  profile=profile)
        self.assertEqual(plan.blocking_issues, [])
        self.assertEqual(plan.assumptions, [])
        self.assertEqual(plan.net_constraints["VBUS"].clearance_mil, profile.derive_clearance_mil("VBUS", "GND"))
        self.assertEqual(plan.net_constraints["VBUS"].min_width_mil, profile.derive_trace_width_mil("VBUS", is_inner=False, layer_idx=1))


if __name__ == "__main__":
    unittest.main()
