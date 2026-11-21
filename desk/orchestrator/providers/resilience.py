"""Timeouts, bounded retries and an ordered fallback chain over model routes.

For each route in order:
  1. capability gate from the descriptor: vision required but absent, or the prompt plus the
     output budget does not fit the context window -> skip the route (recorded, not silent);
  2. credentials missing -> skip;
  3. adapt: tools requested but no native tool calling -> PromptToolProvider; JSON wanted but no
     native JSON mode -> a JSON instruction in the system prompt; thinking control sent only to
     models that support it;
  4. call with a per-attempt timeout bounded by the overall deadline; retry only retryable errors
     (429, 5xx, timeouts, network) with exponential backoff that honours Retry-After, at most
     `max_attempts` times; non-retryable errors (auth, bad request) move straight to the next route.
All routes exhausted -> FallbackExhausted carrying every route's reason.

Zero external dependencies.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterator, List, Optional

from desk.orchestrator.providers.accounting import UsageLedger
from desk.orchestrator.providers.base import (ChatRequest, ChatResponse, ModelProvider, ModelRoute, ProviderError,
                                              StreamEvent, Usage, estimate_tokens, json_instruction)
from desk.orchestrator.providers.prompt_tools import PromptToolProvider


@dataclass
class RetryPolicy:
    max_attempts: int = 3          # per route, including the first call
    base_delay_s: float = 0.5
    max_delay_s: float = 8.0

    def delay(self, attempt: int, retry_after: Optional[float] = None) -> float:
        d = min(self.max_delay_s, self.base_delay_s * (2 ** (attempt - 1)))
        if retry_after is not None and retry_after > 0:
            d = max(d, min(retry_after, self.max_delay_s))
        return d


class FallbackExhausted(ProviderError):
    def __init__(self, reasons: List[Dict[str, Any]]):
        self.reasons = reasons
        text = " | ".join(f"{r['route']}: {r['reason']}" for r in reasons) or "no routes configured"
        super().__init__("all model routes failed: " + text, kind="exhausted", retryable=False)


def _with_json_instruction(messages: List[Dict[str, Any]], schema: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    instr = json_instruction(schema)
    out = [dict(m) for m in messages]
    for m in out:
        if m.get("role") == "system":
            m["content"] = (m.get("content") or "") + "\n\n" + instr
            return out
    return [{"role": "system", "content": instr}] + out


class ResilientClient:
    def __init__(self, registry, routes: List[ModelRoute], retry: Optional[RetryPolicy] = None,
                 ledger: Optional[UsageLedger] = None, sleep: Callable[[float], None] = time.sleep):
        self.registry = registry
        self.routes = list(routes)
        self.retry = retry or RetryPolicy()
        self.ledger = ledger if ledger is not None else UsageLedger()
        self.sleep = sleep
        self.last_reasons: List[Dict[str, Any]] = []

    # ---- planning ----------------------------------------------------------------------------
    def _prepare(self, route: ModelRoute, messages, tools, json_mode, json_schema, max_tokens, temperature,
                 timeout, thinking, requires_vision):
        """Return (provider, request, descriptor) or raise ProviderError(kind="unsupported"/"config")."""
        desc = self.registry.descriptor(route)
        if requires_vision and not desc.vision:
            raise ProviderError("model has no vision capability", kind="unsupported")
        need = estimate_tokens(messages, tools) + int(max_tokens)
        if need > desc.context_window:
            raise ProviderError(f"needs ~{need} tokens, context window is {desc.context_window}", kind="unsupported")
        provider: ModelProvider = self.registry.get(route.provider)
        ok, why = provider.configured()
        if not ok:
            raise ProviderError(why, kind="config")
        if tools and not desc.native_tools:
            provider = PromptToolProvider(provider)
        native_json = json_mode and desc.structured_output
        msgs = _with_json_instruction(messages, json_schema) if (json_mode and not native_json) else list(messages)
        req = ChatRequest(model=route.model, messages=msgs, tools=tools or None, json_mode=native_json,
                          json_schema=json_schema, max_tokens=int(max_tokens), temperature=temperature, timeout=timeout,
                          thinking=thinking if desc.thinking_controllable else None)
        return provider, req, desc

    @staticmethod
    def _fill_usage(resp: ChatResponse, req: ChatRequest) -> None:
        if resp.usage.input_tokens or resp.usage.output_tokens:
            return
        resp.usage = Usage(estimate_tokens(req.messages, req.tools), len(resp.text) // 4 + (1 if resp.text else 0), True)

    # ---- execution ---------------------------------------------------------------------------
    def chat(self, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None, tool_choice: str = "auto",
             json_mode: bool = False, json_schema: Optional[Dict[str, Any]] = None, max_tokens: int = 2048,
             temperature: float = 0.0, timeout: float = 60.0, thinking: Optional[str] = None,
             requires_vision: bool = False, deadline_s: Optional[float] = None) -> ChatResponse:
        t_start = time.monotonic()
        reasons: List[Dict[str, Any]] = []
        self.last_reasons = reasons
        for route in self.routes:
            try:
                provider, req, desc = self._prepare(route, messages, tools, json_mode, json_schema, max_tokens,
                                                    temperature, timeout, thinking, requires_vision)
            except ProviderError as e:
                reasons.append({"route": str(route), "reason": f"skipped: {e}", "kind": e.kind})
                continue
            req.tool_choice = tool_choice
            for attempt in range(1, max(1, self.retry.max_attempts) + 1):
                remaining = None if deadline_s is None else deadline_s - (time.monotonic() - t_start)
                if remaining is not None and remaining <= 0:
                    reasons.append({"route": str(route), "reason": "overall deadline reached", "kind": "timeout"})
                    raise FallbackExhausted(reasons)
                req.timeout = timeout if remaining is None else max(1.0, min(timeout, remaining))
                t0 = time.perf_counter()
                try:
                    resp = provider.chat(req)
                except ProviderError as e:
                    self.ledger.record(route, desc, None, (time.perf_counter() - t0) * 1000, ok=False,
                                       via=getattr(provider, "kind", "native"), attempt=attempt, error=f"{e.kind}: {e}")
                    if e.retryable and attempt < self.retry.max_attempts:
                        self.sleep(self.retry.delay(attempt, e.retry_after))
                        continue
                    reasons.append({"route": str(route), "reason": f"{e.kind}: {e} (attempt {attempt})", "kind": e.kind})
                    break
                self._fill_usage(resp, req)
                self.ledger.record(route, desc, resp.usage, resp.latency_ms or (time.perf_counter() - t0) * 1000,
                                   ok=True, via=resp.via, attempt=attempt)
                resp.provider, resp.model = route.provider, resp.model or route.model
                return resp
        raise FallbackExhausted(reasons)

    def stream(self, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None, json_mode: bool = False,
               json_schema: Optional[Dict[str, Any]] = None, max_tokens: int = 2048, temperature: float = 0.0,
               timeout: float = 60.0, thinking: Optional[str] = None) -> Iterator[StreamEvent]:
        """Stream from the first route that starts. Fallback happens only before the first event:
        text already shown to the caller is never silently replaced by another model's answer."""
        reasons: List[Dict[str, Any]] = []
        self.last_reasons = reasons
        for route in self.routes:
            try:
                provider, req, desc = self._prepare(route, messages, tools, json_mode, json_schema, max_tokens,
                                                    temperature, timeout, thinking, False)
            except ProviderError as e:
                reasons.append({"route": str(route), "reason": f"skipped: {e}", "kind": e.kind})
                continue
            if not desc.streaming or isinstance(provider, PromptToolProvider):
                events = ModelProvider.stream(provider, req)  # one-chunk stream over chat()
            else:
                events = provider.stream(req)
            started = False
            t0 = time.perf_counter()
            try:
                for ev in events:
                    started = True
                    if ev.type == "done" and ev.response is not None:
                        self._fill_usage(ev.response, req)
                        self.ledger.record(route, desc, ev.response.usage, (time.perf_counter() - t0) * 1000, ok=True,
                                           via=ev.response.via)
                    yield ev
                return
            except ProviderError as e:
                self.ledger.record(route, desc, None, (time.perf_counter() - t0) * 1000, ok=False, error=f"{e.kind}: {e}")
                if started:
                    raise
                reasons.append({"route": str(route), "reason": f"{e.kind}: {e}", "kind": e.kind})
        raise FallbackExhausted(reasons)
