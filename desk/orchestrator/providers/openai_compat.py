"""OpenAI-compatible chat-completions provider (stdlib urllib).

One adapter covers every endpoint that speaks `/v1/chat/completions` + `/v1/models`: OpenAI,
xAI Grok, NVIDIA NIM, and local servers (Ollama, llama.cpp `llama-server`, vLLM). Endpoint
differences are preset data (catalog.PRESETS), not code branches, except thinking control:
NIM takes `chat_template_kwargs.enable_thinking` (verified 2026-11-11, see http_adapter.py),
other endpoints get `reasoning_effort` only when a level is asked for.

Zero external dependencies.
"""
from __future__ import annotations

import json
import time
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple, Union

from desk.orchestrator.providers.base import (ChatRequest, ChatResponse, ModelProvider, ProviderError, StreamEvent,
                                              ToolCall, Transport, UrllibTransport, Usage, sse_data)

KeySource = Union[None, str, Callable[[], Optional[str]]]


def _clean_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Strip DESK-only keys (provider_meta) so strict endpoints do not reject the request."""
    out = []
    for m in messages:
        m2 = {k: v for k, v in m.items() if k != "provider_meta"}
        if m2.get("tool_calls"):
            m2["tool_calls"] = [{k: v for k, v in c.items() if k != "provider_meta"} for c in m2["tool_calls"]]
        out.append(m2)
    return out


def key_value(source: KeySource) -> Optional[str]:
    k = source() if callable(source) else source
    return (k or "").strip() or None


class OpenAICompatProvider(ModelProvider):
    kind = "openai_compat"

    def __init__(self, name: str, base_url: str, api_key: KeySource = None, key_setting: Optional[str] = None,
                 transport: Optional[Transport] = None, thinking_style: Optional[str] = None, local: bool = False):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.key_setting = key_setting
        self.transport = transport or UrllibTransport()
        self.thinking_style = thinking_style
        self.local = local

    # ---- credentials -----------------------------------------------------------------------
    def configured(self) -> Tuple[bool, str]:
        if self.key_setting is None:
            return True, f"local endpoint {self.base_url} (no key)"
        if key_value(self._api_key):
            return True, f"key from {self.key_setting} (value never logged)"
        return False, f"no API key: set {self.key_setting} or run desk.py auth configure {self.name}"

    def _headers(self) -> Dict[str, str]:
        h = {"Content-Type": "application/json", "Accept": "application/json"}
        key = key_value(self._api_key)
        if key:
            h["Authorization"] = f"Bearer {key}"
        elif self.key_setting is not None:
            raise ProviderError(f"no API key for provider '{self.name}': set {self.key_setting}", kind="config")
        return h

    # ---- request ---------------------------------------------------------------------------
    def build_body(self, req: ChatRequest, stream: bool = False) -> Dict[str, Any]:
        body: Dict[str, Any] = {"model": req.model, "messages": _clean_messages(req.messages),
                                "temperature": req.temperature, "max_tokens": int(req.max_tokens)}
        if req.tools:
            body["tools"] = req.tools
            body["tool_choice"] = req.tool_choice
        if req.json_mode:
            body["response_format"] = {"type": "json_object"}
        level = (req.thinking or "").lower()
        if self.thinking_style == "nim":
            if level == "off":
                body["chat_template_kwargs"] = {"enable_thinking": False}
                body["reasoning_effort"] = "none"
            elif level in ("low", "medium", "high"):
                body["reasoning_effort"] = level
        elif level in ("low", "medium", "high"):
            body["reasoning_effort"] = level
        if stream:
            body["stream"] = True
        return body

    @staticmethod
    def _usage(u: Optional[Dict[str, Any]]) -> Usage:
        u = u or {}
        return Usage(input_tokens=int(u.get("prompt_tokens") or 0), output_tokens=int(u.get("completion_tokens") or 0))

    def parse(self, resp: Dict[str, Any], model: str, t0: float) -> ChatResponse:
        try:
            choice = resp["choices"][0]
        except (KeyError, IndexError, TypeError):
            raise ProviderError("malformed completion response (no choices)", kind="bad_response")
        msg = choice.get("message") or {}
        calls = [ToolCall.from_openai(c) for c in (msg.get("tool_calls") or [])]
        return ChatResponse(provider=self.name, model=resp.get("model") or model, text=(msg.get("content") or ""),
                            tool_calls=calls, finish_reason=choice.get("finish_reason"),
                            usage=self._usage(resp.get("usage")), latency_ms=round((time.perf_counter() - t0) * 1000, 2))

    def chat(self, req: ChatRequest) -> ChatResponse:
        t0 = time.perf_counter()
        resp = self.transport.post_json(self.base_url + "/chat/completions", self._headers(), self.build_body(req), req.timeout)
        return self.parse(resp, req.model, t0)

    def stream(self, req: ChatRequest) -> Iterator[StreamEvent]:
        t0 = time.perf_counter()
        text: List[str] = []
        calls: Dict[int, Dict[str, Any]] = {}
        usage, finish, model = Usage(), None, req.model
        lines = self.transport.stream_lines(self.base_url + "/chat/completions", self._headers(),
                                            self.build_body(req, stream=True), req.timeout)
        for _event, data in sse_data(lines):
            try:
                chunk = json.loads(data)
            except ValueError:
                continue
            model = chunk.get("model") or model
            if chunk.get("usage"):
                usage = self._usage(chunk["usage"])
            for ch in chunk.get("choices") or []:
                delta = ch.get("delta") or {}
                if delta.get("content"):
                    text.append(delta["content"])
                    yield StreamEvent(type="text", text=delta["content"])
                for tc in delta.get("tool_calls") or []:
                    slot = calls.setdefault(int(tc.get("index", 0)), {"id": "", "name": "", "args": []})
                    slot["id"] = tc.get("id") or slot["id"]
                    fn = tc.get("function") or {}
                    slot["name"] = fn.get("name") or slot["name"]
                    if fn.get("arguments"):
                        slot["args"].append(fn["arguments"])
                finish = ch.get("finish_reason") or finish
        tool_calls = []
        for i in sorted(calls):
            s = calls[i]
            tc = ToolCall.from_openai({"id": s["id"] or f"call_{i}",
                                       "function": {"name": s["name"], "arguments": "".join(s["args"])}})
            tool_calls.append(tc)
            yield StreamEvent(type="tool_call", tool_call=tc)
        resp = ChatResponse(provider=self.name, model=model, text="".join(text), tool_calls=tool_calls,
                            finish_reason=finish, usage=usage, latency_ms=round((time.perf_counter() - t0) * 1000, 2))
        yield StreamEvent(type="done", response=resp)

    def list_models(self, timeout: float = 10.0) -> List[str]:
        data = self.transport.get_json(self.base_url + "/models", self._headers(), timeout)
        return [m.get("id") for m in (data.get("data") or []) if isinstance(m, dict) and m.get("id")]
