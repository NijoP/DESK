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

    def test_07_fallback_does_not_leak_provider_model(self):
        # A model name chosen for the first provider must never be passed to the fallback provider.
        seen = {}

        class RecordingAdapter(MockAdapter):
            def execute(self, task):
                seen[self.name] = task.preferred_model
                return super().execute(task)

        ProviderRegistry.register("agy", RecordingAdapter("agy", succeed=False))
        ProviderRegistry.register("pi", RecordingAdapter("pi", succeed=True, output_text="pi ok"))

        task = TaskRequest(task_type="fast", prompt="q", execution_level=1)
        res = CapabilityRouter.dispatch(task)

        self.assertTrue(res.success)
        self.assertEqual(seen["agy"], "gemini-3.8-flash-low")
        self.assertIsNone(seen["pi"])              # pi runs with its own default, not the Gemini name
        self.assertIsNone(task.preferred_model)    # caller's request object is untouched

    def test_08_tier_timeouts_applied_when_unset(self):
        seen = {}

        class RecordingAdapter(MockAdapter):
            def execute(self, task):
                seen[task.execution_level] = task.timeout_sec
                return super().execute(task)

        ProviderRegistry.register("agy", RecordingAdapter("agy"))
        ProviderRegistry.register("pi", RecordingAdapter("pi"))

        CapabilityRouter.dispatch(TaskRequest(prompt="q", execution_level=1))
        CapabilityRouter.dispatch(TaskRequest(prompt="q", execution_level=2))
        self.assertEqual(seen[1], 30.0)
        self.assertEqual(seen[2], 90.0)

        explicit = TaskRequest(prompt="q", execution_level=1, timeout_sec=7.5)
        CapabilityRouter.dispatch(explicit)
        self.assertEqual(seen[1], 7.5)

    def test_09_l3_runs_providers_concurrently(self):
        class SlowAdapter(MockAdapter):
            def execute(self, task):
                time.sleep(0.25)
                return super().execute(task)

        ProviderRegistry.register("agy", SlowAdapter("agy", output_text="A"))
        ProviderRegistry.register("pi", SlowAdapter("pi", output_text="B"))

        t0 = time.perf_counter()
        res = CapabilityRouter.dispatch(TaskRequest(prompt="q", execution_level=3))
        elapsed = time.perf_counter() - t0

        self.assertTrue(res.success)
        self.assertEqual(res.provider, "dual_consensus")
        self.assertLess(elapsed, 0.45)  # sequential would be >= 0.5 s

    def test_10_l4_uses_configured_frontier_model(self):
        import os
        seen = {}

        class RecordingAdapter(MockAdapter):
            def execute(self, task):
                seen["model"] = task.preferred_model
                return super().execute(task)

        ProviderRegistry.register("agy", RecordingAdapter("agy"))
        old = os.environ.get("DESK_FRONTIER_MODEL")
        os.environ["DESK_FRONTIER_MODEL"] = "test-frontier-model"
        try:
            res = CapabilityRouter.dispatch(TaskRequest(prompt="q", execution_level=4))
        finally:
            if old is None:
                os.environ.pop("DESK_FRONTIER_MODEL", None)
            else:
                os.environ["DESK_FRONTIER_MODEL"] = old
        self.assertTrue(res.success)
        self.assertEqual(seen["model"], "test-frontier-model")

    def test_11_l4_falls_back_to_provider_reported_model(self):
        import os

        class HealthAdapter(MockAdapter):
            def check_health(self):
                h = super().check_health()
                h.supported_models = ["gemini-3.8-flash-low", "gemini-3.8-pro"]
                return h

            def execute(self, task):
                return TaskResult(task_id=task.task_id, success=True, provider="agy",
                                  model=task.preferred_model, output_text="ok")

        ProviderRegistry.register("agy", HealthAdapter("agy"))
        os.environ.pop("DESK_FRONTIER_MODEL", None)
        res = CapabilityRouter.dispatch(TaskRequest(prompt="q", execution_level=4))
        self.assertTrue(res.success)
        self.assertEqual(res.model, "gemini-3.8-pro")

    def test_12_pi_command_is_argument_list_with_schema_in_system_prompt(self):
        pi = PiAdapter(executable_path="pi")
        task = TaskRequest(prompt='x" & calc.exe', output_schema={"type": "object"}, preferred_model="m")
        cmd = pi.build_command(task)
        self.assertIsInstance(cmd, list)
        self.assertEqual(cmd[2], 'x" & calc.exe')  # passed verbatim as one argv entry, never via a shell
        self.assertIn("--model", cmd)
        self.assertIn("--system-prompt", cmd)
        self.assertIn('"type": "object"', cmd[cmd.index("--system-prompt") + 1])

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
