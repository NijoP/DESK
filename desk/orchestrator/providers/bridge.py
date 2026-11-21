"""Bridges from the provider layer to DESK's existing orchestrator interfaces.

* ProviderChatAdapter  - the `chat_completion(...)` shape agent_loop.run_agent already calls, backed
                         by a ResilientClient (retry, fallback, capability adaptation, accounting).
* ProviderTaskAdapter  - the `execute(TaskRequest) -> TaskResult` / `check_health()` shape the L0-L4
                         CapabilityRouter registry expects, so any provider can serve a router tier.
* adapter_for_model    - "provider:model" (plus optional fallbacks) -> ProviderChatAdapter.

Zero external dependencies.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from desk.orchestrator.protocol import ProviderHealth, TaskRequest, TaskResult
from desk.orchestrator.providers.accounting import UsageLedger
from desk.orchestrator.providers.base import ModelRoute, ProviderError
from desk.orchestrator.providers.registry import ModelProviderRegistry, get_provider_registry
from desk.orchestrator.providers.resilience import ResilientClient, RetryPolicy


class ProviderChatAdapter:
    """Legacy-shaped chat adapter: returns {"message", "finish_reason", "usage", "provider", "via"}
    or {"error"}; never raises, exactly like http_adapter.OpenAICompatAdapter.chat_completion."""

    def __init__(self, client: ResilientClient):
        self.client = client
        self.ledger = client.ledger
        self.routes = client.routes

    @property
    def label(self) -> str:
        return str(self.routes[0]) if self.routes else "none"

    def chat_completion(self, messages: List[Dict[str, Any]], model: Optional[str] = None,
                        tools: Optional[List[Dict[str, Any]]] = None, tool_choice: str = "auto",
                        thinking: Optional[str] = "off", max_tokens: Optional[int] = None,
                        timeout: float = 120.0, temperature: float = 0.0, json_mode: bool = False) -> Dict[str, Any]:
        from desk import config as deskcfg
        try:
            resp = self.client.chat(messages, tools=tools, tool_choice=tool_choice, json_mode=json_mode,
                                    max_tokens=int(max_tokens or deskcfg.get_int("DESK_HTTP_MAX_TOKENS", 2048)),
                                    temperature=temperature, timeout=timeout, thinking=thinking)
        except ProviderError as e:
            return {"error": str(e)}
        u = resp.usage
        return {"message": {"content": resp.text, "tool_calls": [c.to_openai() for c in resp.tool_calls]},
                "finish_reason": resp.finish_reason, "provider": resp.provider, "model": resp.model, "via": resp.via,
                "usage": {"prompt_tokens": u.input_tokens, "completion_tokens": u.output_tokens,
                          "total_tokens": u.total_tokens}}


def adapter_for_model(spec: str, fallbacks: Optional[List[str]] = None,
                      registry: Optional[ModelProviderRegistry] = None, ledger: Optional[UsageLedger] = None,
                      retry: Optional[RetryPolicy] = None) -> ProviderChatAdapter:
    reg = registry or get_provider_registry()
    routes = [reg.parse_route(spec)] + [reg.parse_route(f) for f in (fallbacks or []) if f]
    return ProviderChatAdapter(ResilientClient(reg, routes, retry=retry, ledger=ledger))


def is_provider_route(spec: Optional[str], registry: Optional[ModelProviderRegistry] = None) -> bool:
    """True when `spec` is written "provider:model" with a registered provider."""
    if not spec or ":" not in spec:
        return False
    return (registry or get_provider_registry()).has(spec.split(":", 1)[0])


class ProviderTaskAdapter:
    """Serve CapabilityRouter tiers from any registered provider."""

    def __init__(self, provider: str, registry: Optional[ModelProviderRegistry] = None,
                 default_models: Optional[Dict[int, str]] = None, ledger: Optional[UsageLedger] = None,
                 retry: Optional[RetryPolicy] = None):
        self.name = provider
        self.registry = registry or get_provider_registry()
        self.default_models = dict(default_models or {})
        self.ledger = ledger if ledger is not None else UsageLedger()
        self.retry = retry or RetryPolicy(max_attempts=2)

    def check_health(self, timeout_sec: float = 8.0) -> ProviderHealth:
        """Configuration check only (no network): whether credentials are present."""
        t0 = time.time()
        try:
            ok, why = self.registry.get(self.name).configured()
        except ProviderError as e:
            ok, why = False, str(e)
        return ProviderHealth(provider_name=self.name, available=ok, cli_path="", last_checked=t0,
                              supported_models=sorted(set(self.default_models.values())), status_message=why)

    def execute(self, task: TaskRequest) -> TaskResult:
        t0 = time.perf_counter()
        model = task.preferred_model or self.default_models.get(task.execution_level)

        def fail(msg: str) -> TaskResult:
            return TaskResult(task_id=task.task_id, success=False, provider=self.name, model=model or "unset",
                              output_text="", latency_ms=round((time.perf_counter() - t0) * 1000, 2),
                              execution_level=task.execution_level, error=msg)

        if not model:
            return fail(f"No model configured for provider '{self.name}' at L{task.execution_level}.")
        from desk.orchestrator.http_adapter import OpenAICompatAdapter, _extract_json
        messages: List[Dict[str, Any]] = []
        if task.system_prompt:
            messages.append({"role": "system", "content": task.system_prompt})
        messages.append({"role": "user", "content": OpenAICompatAdapter.user_content(task.prompt, task.images)})
        client = ResilientClient(self.registry, [ModelRoute(self.name, model)], retry=self.retry, ledger=self.ledger)
        try:
            resp = client.chat(messages, json_mode=bool(task.output_schema), json_schema=task.output_schema,
                               timeout=task.timeout_sec or 60.0, thinking=task.thinking_level,
                               requires_vision=bool(task.requires_vision or task.images))
        except ProviderError as e:
            return fail(str(e))
        content = (resp.text or "").strip()
        parsed = _extract_json(content)
        latency = round((time.perf_counter() - t0) * 1000, 2)
        if task.output_schema and not isinstance(parsed, dict):
            return TaskResult(task_id=task.task_id, success=False, provider=self.name, model=resp.model,
                              output_text=content, latency_ms=latency, execution_level=task.execution_level,
                              error="Schema requested but model returned no JSON object.")
        return TaskResult(task_id=task.task_id, success=bool(content), provider=self.name, model=resp.model,
                          output_text=content, output_json=parsed if isinstance(parsed, dict) else None,
                          latency_ms=latency, execution_level=task.execution_level,
                          error=None if content else f"Empty content (finish_reason={resp.finish_reason})")


def register_with_router(names: List[str], registry: Optional[ModelProviderRegistry] = None) -> List[str]:
    """Register providers (e.g. ["openai", "anthropic", "gemini", "ollama"]) with the L0-L4 router.
    Their tier default model is the first route for that provider in the allocation policy.
    Opt-in: nothing is registered at import time, so DESK_PROVIDER_ORDER behaviour is unchanged,
    and the built-in "agy", "pi" and "nvidia" router adapters are never replaced."""
    from desk.orchestrator.providers.allocation import load_policy
    from desk.orchestrator.router import ProviderRegistry
    reg = registry or get_provider_registry()
    tiers = load_policy().get("tiers") or {}
    done = []
    for n in names:
        if n in ("agy", "pi", "nvidia") or not reg.has(n):
            continue
        defaults: Dict[int, str] = {}
        for lvl in (1, 2, 3, 4):
            for r in tiers.get(str(lvl)) or []:
                route = reg.parse_route(r)
                if route.provider == n:
                    defaults[lvl] = route.model
                    break
        ProviderRegistry.register(n, ProviderTaskAdapter(n, reg, defaults))
        done.append(n)
    return done
