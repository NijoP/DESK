"""Capability-Based Model Router and Dispatch Engine for DESK.
Implements the 5-tier execution hierarchy:
L0 — Deterministic execution (Zero LLM call)
L1 — Simple / fast reasoning (One fast model with fallback)
L2 — Complex reasoning (One capable model + deterministic validation gate)
L3 — High-risk decisions (Dual independent model review, run in parallel, resolved by evidence)
L4 — Frontier escalation (Complex contradictions or high-risk design pivots)

Model selection per tier and provider is configurable through environment
variables so cheap / free endpoints can be assigned to the low tiers without
touching code:

    DESK_L1_MODEL_{AGY,PI,NVIDIA}         fast reasoning
    DESK_L2_MODEL_{AGY,PI,NVIDIA}         capable + validated
    DESK_L3_MODEL_{AGY,PI,NVIDIA}         dual review
    DESK_PROVIDER_ORDER                   comma list, e.g. "nvidia,pi,agy" (default "agy,pi")
    DESK_L3_PROVIDERS                     the two providers used for dual review (default "agy,pi")
    DESK_FRONTIER_PROVIDER                provider for L4 (default: first of DESK_PROVIDER_ORDER)
    DESK_FRONTIER_MODEL                   model id served by that provider

Providers: "agy" (Gemini CLI), "pi" (Pi coding agent CLI, multi-provider) and
"nvidia" (direct HTTP to the OpenAI-compatible NVIDIA NIM endpoint; no harness
context, so an L1 call costs ~150 tokens instead of ~4k-24k through a CLI).

Per-tier timeouts apply when the caller leaves TaskRequest.timeout_sec unset:

    DESK_L1_TIMEOUT, DESK_L2_TIMEOUT, DESK_L3_TIMEOUT, DESK_L4_TIMEOUT

Zero external dependencies.
"""
import os
from desk import config as deskcfg
import re
import time
import json
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Any, Callable
from desk.orchestrator.protocol import TaskRequest, TaskResult, ProviderHealth
from desk.orchestrator.agy_adapter import AGYAdapter
from desk.orchestrator.pi_adapter import PiAdapter
from desk.orchestrator.http_adapter import OpenAICompatAdapter
from desk.profiler import TelemetryCollector

# Default model per (tier, provider). Pi has no fixed default: it uses whatever
# the operator saved as the Pi default model unless an env override is set.
# NVIDIA defaults are the three models verified on 2026-11-11 (see capabilities.py).
_DEFAULT_MODELS: Dict[int, Dict[str, Optional[str]]] = {
    1: {"agy": "gemini-3.8-flash-low", "pi": None, "nvidia": "nvidia/nemotron-3.5-lightning-30b-a3b"},
    2: {"agy": "gemini-3.8-flash-high", "pi": None, "nvidia": "nvidia/nemotron-3.5-super-vl-120b-a12b"},
    3: {"agy": "gemini-3.8-flash-high", "pi": None, "nvidia": "nvidia/nemotron-3-ultra-550b-a55b"},
    4: {"agy": None, "pi": None, "nvidia": "nvidia/nemotron-3-ultra-550b-a55b"},
}

# Seconds. L1 is short on purpose: a fast model that has not answered in 30 s
# is cheaper to fail over than to wait for. Reasoning models at L3/L4 need room.
_DEFAULT_TIMEOUTS: Dict[int, float] = {1: 30.0, 2: 90.0, 3: 180.0, 4: 300.0}

# Thinking is off for the cheap tiers: measured on 2026-11-11, a Nemotron 3.5 model spent
# its whole 1,500-token budget on reasoning for a one-line question (40-50 s, empty
# answer) with thinking on, and answered in about 1 s with it off.
_DEFAULT_THINKING: Dict[int, str] = {1: "off", 2: "off", 3: "medium", 4: "high"}

_FRONTIER_HINT = re.compile(r"pro|ultra|opus|sonnet|frontier|max|large", re.I)


def _env(name: str) -> Optional[str]:
    """Configured value: environment, then ~/.desk/config.json, then desk.config.json (desk/config.py)."""
    v = (deskcfg.get(name) or "").strip()
    return v or None


def tier_model(level: int, provider: str) -> Optional[str]:
    """Resolve the configured model for a tier/provider pair (env override first)."""
    override = _env(f"DESK_L{level}_MODEL_{provider.upper()}")
    if override:
        return override
    return _DEFAULT_MODELS.get(level, {}).get(provider)


def tier_timeout(level: int) -> float:
    override = _env(f"DESK_L{level}_TIMEOUT")
    if override:
        try:
            return float(override)
        except ValueError:
            pass
    return _DEFAULT_TIMEOUTS.get(level, 60.0)


def tier_thinking(level: int) -> str:
    return _env(f"DESK_L{level}_THINKING") or _DEFAULT_THINKING.get(level, "off")


def _task_for(task: TaskRequest, provider: str, level: int) -> TaskRequest:
    """Return an isolated copy of the task bound to one provider.

    The original request is never mutated, so a model name chosen for one
    provider can never leak into the fallback call to another provider.
    """
    from desk.orchestrator.capabilities import get_registry

    t = TaskRequest(**task.to_dict())
    t.preferred_provider = provider
    if not t.preferred_model:
        t.preferred_model = tier_model(level, provider)
    if t.requires_vision or t.images:
        t.requires_vision = True
        t.preferred_model = get_registry().ensure_capability(provider, t.preferred_model, "vision") or t.preferred_model
    if not t.timeout_sec:
        t.timeout_sec = tier_timeout(level)
    if not t.thinking_level:
        t.thinking_level = tier_thinking(level)
    return t


class ProviderRegistry:
    _providers: Dict[str, Any] = {}
    _health_cache: Dict[str, ProviderHealth] = {}

    @classmethod
    def register(cls, name: str, adapter_instance: Any):
        cls._providers[name] = adapter_instance
        cls._health_cache.pop(name, None)

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
ProviderRegistry.register("nvidia", OpenAICompatAdapter("nvidia"))


def provider_order() -> List[str]:
    raw = _env("DESK_PROVIDER_ORDER") or "agy,pi"
    return [p.strip() for p in raw.split(",") if p.strip()]


def l3_providers() -> List[str]:
    raw = _env("DESK_L3_PROVIDERS") or "agy,pi"
    return [p.strip() for p in raw.split(",") if p.strip()][:2]


def _failure(task: TaskRequest, level: int, provider: str, model: str, error: str, t0: float) -> TaskResult:
    return TaskResult(
        task_id=task.task_id,
        success=False,
        provider=provider,
        model=model,
        output_text="",
        latency_ms=round((time.perf_counter() - t0) * 1000, 2),
        execution_level=level,
        error=error,
    )


def _validate(res: TaskResult, validator: Optional[Callable[[TaskResult], bool]]) -> bool:
    if not validator:
        return True
    try:
        return bool(validator(res))
    except Exception:
        return False


class CapabilityRouter:

    @staticmethod
    def _provider_order(task: TaskRequest) -> List[str]:
        order = provider_order()
        if task.preferred_provider:
            return [task.preferred_provider] + [p for p in order if p != task.preferred_provider]
        return order

    @staticmethod
    def dispatch(task: TaskRequest,
                 deterministic_handler: Optional[Callable[[], Any]] = None,
                 validator: Optional[Callable[[TaskResult], bool]] = None) -> TaskResult:
        """Route and execute a task across the L0-L4 capability hierarchy."""
        telemetry = TelemetryCollector.get_instance()
        t0 = time.perf_counter()
        level = task.execution_level

        # ------------------------------------------------------------- L0: DETERMINISTIC EXECUTION
        if level == 0:
            if not deterministic_handler:
                return _failure(task, 0, "deterministic", "none",
                                "Execution level 0 requested but no deterministic_handler provided.", t0)
            try:
                res = deterministic_handler()
                telemetry.record_cache_hit()
                return TaskResult(
                    task_id=task.task_id,
                    success=True,
                    provider="deterministic",
                    model="rule_engine",
                    output_text=str(res) if not isinstance(res, (dict, list)) else json.dumps(res),
                    output_json=res if isinstance(res, (dict, list)) else None,
                    latency_ms=round((time.perf_counter() - t0) * 1000, 2),
                    execution_level=0
                )
            except Exception as e:
                return _failure(task, 0, "deterministic", "rule_engine",
                                f"Deterministic execution failed: {str(e)[:300]}", t0)

        providers_to_try = CapabilityRouter._provider_order(task)

        # ------------------------------------------------------------- L1: FAST REASONING
        if level == 1:
            errors = []
            for p_name in providers_to_try:
                adapter = ProviderRegistry.get(p_name)
                if not adapter:
                    continue
                res = adapter.execute(_task_for(task, p_name, 1))
                if res.success:
                    return res
                errors.append(f"{p_name}: {res.error}")
            return _failure(task, 1, "none", "none",
                            f"All L1 providers failed for task {task.task_id}. " + " | ".join(errors), t0)

        # ------------------------------------------------------------- L2: CAPABLE + VALIDATED
        elif level == 2:
            errors = []
            for p_name in providers_to_try:
                adapter = ProviderRegistry.get(p_name)
                if not adapter:
                    continue
                res = adapter.execute(_task_for(task, p_name, 2))
                if not res.success:
                    errors.append(f"{p_name}: {res.error}")
                    continue
                if not _validate(res, validator):
                    errors.append(f"{p_name}: deterministic validation rejected the model output")
                    continue
                return res
            return _failure(task, 2, "none", "none",
                            "L2 execution failed or was rejected by validation. " + " | ".join(errors), t0)

        # ------------------------------------------------------------- L3: DUAL INDEPENDENT REVIEW
        elif level == 3:
            jobs = []
            for p_name in l3_providers():
                adapter = ProviderRegistry.get(p_name)
                if adapter:
                    jobs.append((p_name, adapter, _task_for(task, p_name, 3)))

            if not jobs:
                return _failure(task, 3, "dual", "none", "No providers registered for L3 dual review.", t0)

            # Both reviews are independent, so run them concurrently: wall time is
            # the slower of the two instead of the sum.
            with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
                futures = [(name, pool.submit(adapter.execute, t)) for name, adapter, t in jobs]
                outcomes = []
                for name, fut in futures:
                    try:
                        outcomes.append((name, fut.result()))
                    except Exception as e:
                        outcomes.append((name, _failure(task, 3, name, "none", f"Adapter raised: {str(e)[:200]}", t0)))

            results = [(name, r) for name, r in outcomes if r.success]
            if not results:
                return _failure(task, 3, "dual", "none",
                                f"All L3 providers ({', '.join(n for n, _ in outcomes)}) failed during dual review.", t0)

            if len(results) == 1:
                name, r = results[0]
                if not _validate(r, validator):
                    r.success = False
                    r.error = "Single available L3 result rejected by validator."
                return r

            (n1, r1), (n2, r2) = results[0], results[1]
            v1, v2 = _validate(r1, validator), _validate(r2, validator)
            if v1 and not v2:
                return r1
            if v2 and not v1:
                return r2
            if not v1 and not v2:
                return _failure(task, 3, "dual", "both",
                                "Both independent models produced outputs rejected by deterministic validation.", t0)

            consensus_text = (f"--- L3 DUAL REVIEW CONSENSUS ---\n[{n1.upper()} ({r1.model})]:\n{r1.output_text}\n\n"
                              f"[{n2.upper()} ({r2.model})]:\n{r2.output_text}")
            return TaskResult(
                task_id=task.task_id,
                success=True,
                provider="dual_consensus",
                model=f"{r1.model}+{r2.model}",
                output_text=consensus_text,
                output_json=r1.output_json or r2.output_json,
                latency_ms=round((time.perf_counter() - t0) * 1000, 2),
                execution_level=3
            )

        # ------------------------------------------------------------- L4: FRONTIER ESCALATION
        elif level >= 4:
            p_name = _env("DESK_FRONTIER_PROVIDER") or provider_order()[0]
            adapter = ProviderRegistry.get(p_name)
            if not adapter:
                return _failure(task, 4, "none", "frontier", f"Frontier provider '{p_name}' not available.", t0)

            model = (task.preferred_model or _env("DESK_FRONTIER_MODEL") or tier_model(4, p_name)
                     or CapabilityRouter._pick_frontier_model(p_name))
            if not model:
                return _failure(task, 4, p_name, "frontier",
                                f"No frontier model configured. Set DESK_FRONTIER_MODEL to a model served by '{p_name}'.", t0)

            t = _task_for(task, p_name, 4)
            t.preferred_model = model
            res = adapter.execute(t)
            if res.success and not _validate(res, validator):
                res.success = False
                res.error = "L4 result rejected by validator."
            return res

        return _failure(task, level, "none", "none", f"Unsupported execution level: {level}", t0)

    @staticmethod
    def _pick_frontier_model(provider: str) -> Optional[str]:
        """Choose the strongest model the provider actually reports serving."""
        health = ProviderRegistry.get_health(provider)
        models = [m for m in (health.supported_models or []) if m and m != "multi-provider"]
        if not models:
            return None
        for m in models:
            if _FRONTIER_HINT.search(m):
                return m
        return models[0]
