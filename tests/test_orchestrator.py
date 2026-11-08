"""Unit tests for Multi-Model Orchestration and Capability Routing (Phases 4 & 5).
"""
import unittest
import time
from desk.orchestrator.protocol import TaskRequest, TaskResult, ProviderHealth
from desk.orchestrator.router import CapabilityRouter, ProviderRegistry
from desk.orchestrator.agy_adapter import AGYAdapter
from desk.orchestrator.pi_adapter import PiAdapter

class MockAdapter:
    def __init__(self, name="mock", succeed=True, output_text="mock output", output_json=None):
        self.name = name
        self.succeed = succeed
        self.output_text = output_text
        self.output_json = output_json or {"mock": "data"}

    def check_health(self):
        return ProviderHealth(
            provider_name=self.name,
            available=self.succeed,
            cli_path=f"/fake/{self.name}",
            supported_models=["mock-model"],
            status_message="Mock OK"
        )

    def execute(self, task: TaskRequest) -> TaskResult:
        if not self.succeed:
            return TaskResult(
                task_id=task.task_id,
                success=False,
                provider=self.name,
                model="mock-fail",
                output_text="",
                error="Simulated mock failure."
            )
        return TaskResult(
            task_id=task.task_id,
            success=True,
            provider=self.name,
            model="mock-model",
            output_text=self.output_text,
            output_json=self.output_json,
            latency_ms=10.0,
            execution_level=task.execution_level
        )

class TestOrchestrator(unittest.TestCase):

    def setUp(self):
        # Register mock adapters for deterministic testing
        ProviderRegistry.register("mock_agy", MockAdapter("mock_agy", succeed=True, output_text="AGY proposal"))
        ProviderRegistry.register("mock_pi", MockAdapter("mock_pi", succeed=True, output_text="Pi proposal"))
        ProviderRegistry.register("mock_fail", MockAdapter("mock_fail", succeed=False))

    def test_01_protocol_serialization(self):
        req = TaskRequest(task_type="routing", prompt="Test prompt", execution_level=2)
        d = req.to_dict()
        self.assertEqual(d["task_type"], "routing")
        self.assertEqual(d["execution_level"], 2)

        restored = TaskRequest.from_dict(d)
        self.assertEqual(restored.task_id, req.task_id)

    def test_02_l0_deterministic_execution_bypass(self):
        # L0 must execute deterministic handler and NEVER call any LLM provider
        called = []
        def handler():
            called.append(True)
            return {"clearance_ok": True}

        task = TaskRequest(task_type="check", prompt="Check clearance", execution_level=0)
        res = CapabilityRouter.dispatch(task, deterministic_handler=handler)

        self.assertTrue(res.success)
        self.assertEqual(res.provider, "deterministic")
        self.assertEqual(res.model, "rule_engine")
        self.assertEqual(res.output_json, {"clearance_ok": True})
        self.assertEqual(len(called), 1)

    def test_03_l1_fast_execution_and_fallback(self):
        # When primary fails, should seamlessly fall back to secondary
        task = TaskRequest(
            task_type="fast",
            prompt="Quick query",
            execution_level=1,
            preferred_provider="mock_fail"
        )
        # Register mock_agy as fallback
        ProviderRegistry.register("mock_fail", MockAdapter("mock_fail", succeed=False))
        ProviderRegistry.register("agy", MockAdapter("agy", succeed=True, output_text="Fallback success"))

        res = CapabilityRouter.dispatch(task)
        self.assertTrue(res.success)
        self.assertEqual(res.output_text, "Fallback success")

    def test_04_l2_capable_with_deterministic_validation(self):
        task = TaskRequest(task_type="complex", prompt="Design block", execution_level=2, preferred_provider="mock_agy")

        # Validator accepts
        def good_validator(r: TaskResult) -> bool:
            return "AGY proposal" in r.output_text

        res = CapabilityRouter.dispatch(task, validator=good_validator)
        self.assertTrue(res.success)

        # Validator rejects
        def bad_validator(r: TaskResult) -> bool:
            return False

        res2 = CapabilityRouter.dispatch(task, validator=bad_validator)
        self.assertFalse(res2.success)
        self.assertIn("rejected", res2.error)

    def test_05_l3_dual_review_consensus(self):
        # Dual review queries both adapters and synthesizes consensus
        ProviderRegistry.register("agy", MockAdapter("agy", succeed=True, output_text="AGY route plan"))
        ProviderRegistry.register("pi", MockAdapter("pi", succeed=True, output_text="Pi route plan"))

        task = TaskRequest(task_type="high_risk", prompt="Audit stackup", execution_level=3)
        res = CapabilityRouter.dispatch(task)

        self.assertTrue(res.success)
        self.assertEqual(res.provider, "dual_consensus")
        self.assertIn("AGY route plan", res.output_text)
        self.assertIn("Pi route plan", res.output_text)

    def test_06_real_adapter_health_check(self):
        # Verify the real installed adapters do not throw unhandled exceptions
        agy = AGYAdapter()
        h_agy = agy.check_health(timeout_sec=2.0)
        self.assertIsInstance(h_agy.available, bool)

        pi = PiAdapter()
        h_pi = pi.check_health(timeout_sec=2.0)
        self.assertIsInstance(h_pi.available, bool)

if __name__ == "__main__":
    unittest.main()
