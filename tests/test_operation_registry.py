"""
Unit tests for the DESK Operation Registry and Execution Contracts.
"""

import unittest

from desk.operation_registry import (
    OperationDescriptor,
    OperationRegistry,
    ReplayPolicy,
    ResourceClass,
    get_operation_registry,
)


class TestOperationRegistry(unittest.TestCase):
    def setUp(self):
        self.registry = get_operation_registry()

    def test_default_operations_present(self):
        expected_ops = ["calc_trace_width", "verify_clearance", "create_copper_zone", "create_checkpoint"]
        for op_id in expected_ops:
            op = self.registry.get(op_id)
            self.assertIsNotNone(op, f"Operation '{op_id}' should be registered.")
            self.assertTrue(op.deterministic)

    def test_calc_trace_width_execution(self):
        from desk import ipc
        result = self.registry.execute("calc_trace_width", {"current_a": 3.0, "temp_rise_c": 10.0})
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["pipeline_stage"], "M3")
        self.assertEqual(result["replay_policy"], "SAFE_READ")
        r = result["result"]
        # One authoritative implementation: the registry must agree with desk.ipc exactly.
        self.assertAlmostEqual(r["trace_width_mil"], ipc.trace_width_mil(3.0, is_inner=False, copper_oz=1.0, temp_rise_c=10.0), places=2)
        self.assertAlmostEqual(r["trace_width_mm"], r["trace_width_mil"] * 0.0254, places=3)
        self.assertIn("IPC-2221", r["reference"])
        self.assertFalse(r["verified_against_standard"])
        self.assertNotIn("2152", self.registry.get("calc_trace_width").description)

    def test_calc_trace_width_refuses_unknown_current(self):
        result = self.registry.execute("calc_trace_width", {"current_a": 0.0, "temp_rise_c": 10.0})
        self.assertTrue(result["result"]["refused"])
        self.assertNotIn("trace_width_mm", result["result"])

    def test_verify_clearance_execution(self):
        # Clearance between (0, 0) and (0, 0.5) is 0.5mm
        res_pass = self.registry.execute("verify_clearance", {"p1": (0, 0), "p2": (0, 0.5), "required_mm": 0.2})
        self.assertTrue(res_pass["result"]["passed"])

        res_fail = self.registry.execute("verify_clearance", {"p1": (0, 0), "p2": (0, 0.1), "required_mm": 0.2})
        self.assertFalse(res_fail["result"]["passed"])

    def test_input_validation_failure(self):
        with self.assertRaises(ValueError):
            # Missing required parameter 'p2'
            self.registry.execute("verify_clearance", {"p1": (0, 0), "required_mm": 0.2})

    def test_custom_operation_registration(self):
        custom_op = OperationDescriptor(
            operation_id="custom_thermal_calc",
            name="Custom Thermal Calculation",
            description="Computes junction temperature rise.",
            deterministic=True,
            resource_class=ResourceClass.LIGHT,
            replay_policy=ReplayPolicy.SAFE_READ,
            pipeline_stage="M2",
            input_schema={"power_w": (int, float), "r_th": (int, float)},
            handler=lambda power_w, r_th: power_w * r_th,
        )
        self.registry.register(custom_op)

        res = self.registry.execute("custom_thermal_calc", {"power_w": 2.0, "r_th": 15.0})
        self.assertEqual(res["result"], 30.0)


if __name__ == "__main__":
    unittest.main()
