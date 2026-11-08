"""Capability-Based Model Router and Dispatch Engine for DESK.
Implements the 5-tier execution hierarchy:
L0 — Deterministic execution (Zero LLM call)
L1 — Simple / fast reasoning (One fast model with fallback)
L2 — Complex reasoning (One capable model + deterministic validation gate)
L3 — High-risk decisions (Dual independent model review resolved by evidence)
L4 — Frontier escalation (Complex contradictions or high-risk design pivots)

Zero external dependencies.
"""
import time
import json
from typing import Dict, List, Optional, Any, Callable
from desk.orchestrator.protocol import TaskRequest, TaskResult, ProviderHealth
from desk.orchestrator.agy_adapter import AGYAdapter
from desk.orchestrator.pi_adapter import PiAdapter
from desk.profiler import TelemetryCollector

class ProviderRegistry:
    _providers: Dict[str, Any] = {}
    _health_cache: Dict[str, ProviderHealth] = {}

    @classmethod
    def register(cls, name: str, adapter_instance: Any):
        cls._providers[name] = adapter_instance

    @classmethod
    def get(cls, name: str) -> Optional[Any]:
        return cls._providers.get(name)

    @classmethod
    def list_providers(cls) -> List[str]:
        return list(cls._providers.keys())

    @classmethod
    def get_health(cls, name: str, force_refresh: bool = False) -> ProviderHealth:
        now = time.time()
        if not force_refresh and name in cls._health_cache:
            h = cls._health_cache[name]
            if (now - h.last_checked) < 60.0:
                return h
        adapter = cls.get(name)
        if not adapter:
            h = ProviderHealth(provider_name=name, available=False, cli_path="", status_message="Provider not registered")
        else:
            h = adapter.check_health()
        cls._health_cache[name] = h
        return h

# Initialize default adapters
ProviderRegistry.register("agy", AGYAdapter())
ProviderRegistry.register("pi", PiAdapter())

class CapabilityRouter:

    @staticmethod
    def dispatch(task: TaskRequest,
                 deterministic_handler: Optional[Callable[[], Any]] = None,
                 validator: Optional[Callable[[TaskResult], bool]] = None) -> TaskResult:
        """Route and execute a task across the L0-L4 capability hierarchy."""
        telemetry = TelemetryCollector.get_instance()
        t0 = time.perf_counter()

        # ------------------------------------------------------------- L0: DETERMINISTIC EXECUTION
        if task.execution_level == 0:
            if not deterministic_handler:
                return TaskResult(
                    task_id=task.task_id,
                    success=False,
                    provider="deterministic",
                    model="none",
                    output_text="",
                    execution_level=0,
                    error="Execution level 0 requested but no deterministic_handler provided."
                )
            try:
                res = deterministic_handler()
                latency_ms = round((time.perf_counter() - t0) * 1000, 2)
                telemetry.record_cache_hit()
                return TaskResult(
                    task_id=task.task_id,
                    success=True,
                    provider="deterministic",
                    model="rule_engine",
                    output_text=str(res) if not isinstance(res, (dict, list)) else json.dumps(res),
                    output_json=res if isinstance(res, (dict, list)) else None,
                    latency_ms=latency_ms,
                    execution_level=0
                )
            except Exception as e:
                latency_ms = round((time.perf_counter() - t0) * 1000, 2)
                return TaskResult(
                    task_id=task.task_id,
                    success=False,
                    provider="deterministic",
                    model="rule_engine",
                    output_text="",
                    latency_ms=latency_ms,
                    execution_level=0,
                    error=f"Deterministic execution failed: {str(e)[:300]}"
                )

        # Provider selection order
        providers_to_try = []
        if task.preferred_provider:
            providers_to_try.append(task.preferred_provider)
            other = "pi" if task.preferred_provider == "agy" else "agy"
            providers_to_try.append(other)
        else:
            providers_to_try = ["agy", "pi"]

        # ------------------------------------------------------------- L1: FAST REASONING
        if task.execution_level == 1:
            for p_name in providers_to_try:
                adapter = ProviderRegistry.get(p_name)
                if not adapter: continue
                # Set model pattern for L1
                if not task.preferred_model and p_name == "agy":
                    task.preferred_model = "gemini-3.8-flash-low"
                res = adapter.execute(task)
                if res.success:
                    return res
            # All providers failed
            return TaskResult(
                task_id=task.task_id,
                success=False,
                provider="none",
                model="none",
                output_text="",
                execution_level=1,
                error=f"All L1 providers failed for task {task.task_id}."
            )

        # ------------------------------------------------------------- L2: CAPABLE + VALIDATED
        elif task.execution_level == 2:
            for p_name in providers_to_try:
                adapter = ProviderRegistry.get(p_name)
                if not adapter: continue
                if not task.preferred_model and p_name == "agy":
                    task.preferred_model = "gemini-3.8-flash-high"

                res = adapter.execute(task)
                if res.success:
                    # Validate output against validator if supplied
                    if validator:
                        is_valid = False
                        try:
                            is_valid = validator(res)
                        except Exception:
                            is_valid = False
                        if not is_valid:
                            # Rejection: invalid response
                            res.success = False
                            res.error = "Deterministic validation rejected the model output."
                            continue
                    return res

            return TaskResult(
                task_id=task.task_id,
                success=False,
                provider="none",
                model="none",
                output_text="",
                execution_level=2,
                error=f"L2 execution failed or was rejected by validation."
            )

        # ------------------------------------------------------------- L3: DUAL INDEPENDENT REVIEW
        elif task.execution_level == 3:
            # Dispatch to both AGY and Pi
            agy_adapter = ProviderRegistry.get("agy")
            pi_adapter = ProviderRegistry.get("pi")

            results = []
            if agy_adapter:
                task_agy = TaskRequest(**task.to_dict())
                task_agy.preferred_model = "gemini-3.8-flash-high"
                r_agy = agy_adapter.execute(task_agy)
                if r_agy.success:
                    results.append(r_agy)

            if pi_adapter:
                task_pi = TaskRequest(**task.to_dict())
                r_pi = pi_adapter.execute(task_pi)
                if r_pi.success:
                    results.append(r_pi)

            if not results:
                return TaskResult(
                    task_id=task.task_id,
                    success=False,
                    provider="dual",
                    model="none",
                    output_text="",
                    execution_level=3,
                    error="Both AGY and Pi failed during L3 dual review."
                )

            # If only one provider succeeded, validate and return it
            if len(results) == 1:
                r = results[0]
                if validator and not validator(r):
                    r.success = False
                    r.error = "Single available L3 result rejected by validator."
                return r

            # Both succeeded: Corroborate results
            r1, r2 = results[0], results[1]
            if validator:
                v1 = validator(r1)
                v2 = validator(r2)
                if v1 and not v2: return r1
                if v2 and not v1: return r2
                if not v1 and not v2:
                    return TaskResult(
                        task_id=task.task_id,
                        success=False,
                        provider="dual",
                        model="both",
                        output_text="",
                        execution_level=3,
                        error="Both independent models produced outputs rejected by deterministic validation."
                    )

            # Both valid: Return synthesized consensus
            latency_ms = round((time.perf_counter() - t0) * 1000, 2)
            consensus_text = f"--- L3 DUAL REVIEW CONSENSUS ---\n[AGY ({r1.model})]:\n{r1.output_text}\n\n[PI ({r2.model})]:\n{r2.output_text}"
            return TaskResult(
                task_id=task.task_id,
                success=True,
                provider="dual_consensus",
                model=f"{r1.model}+{r2.model}",
                output_text=consensus_text,
                output_json=r1.output_json or r2.output_json,
                latency_ms=latency_ms,
                execution_level=3
            )

        # ------------------------------------------------------------- L4: FRONTIER ESCALATION
        elif task.execution_level >= 4:
            adapter = ProviderRegistry.get("agy")
            if adapter:
                task.preferred_model = "claude-sonnet-4-6"
                return adapter.execute(task)
            return TaskResult(
                task_id=task.task_id,
                success=False,
                provider="none",
                model="frontier",
                output_text="",
                execution_level=4,
                error="Frontier provider not available."
            )

        return TaskResult(
            task_id=task.task_id,
            success=False,
            provider="none",
            model="none",
            output_text="",
            execution_level=task.execution_level,
            error=f"Unsupported execution level: {task.execution_level}"
        )
