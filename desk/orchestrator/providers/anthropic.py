"""Anthropic Messages API provider (stdlib urllib, no SDK).

Translates DESK's canonical OpenAI-style conversation to the Messages API:
  * system messages      -> top-level `system`
  * assistant tool_calls -> `tool_use` content blocks
  * tool messages        -> `tool_result` blocks inside a user turn (adjacent turns of one role merged,
                            because the API requires user/assistant alternation)
  * OpenAI tool schemas  -> {name, description, input_schema}

JSON mode is not sent natively; a JSON instruction is added to the system prompt instead.
Extended thinking is not wired (left at the API default).

Zero external dependencies.
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, Iterator, List, Optional, Tuple

from desk.orchestrator.providers.base import (ChatRequest, ChatResponse, ModelProvider, ProviderError, StreamEvent,
                                              ToolCall, Transport, UrllibTransport, Usage, json_instruction, sse_data,
                                              text_content)
from desk.orchestrator.providers.openai_compat import KeySource, key_value

API_VERSION = "2023-06-01"
_CHOICE = {"auto": {"type": "auto"}, "required": {"type": "any"}, "any": {"type": "any"}, "none": {"type": "none"}}


def to_anthropic(messages: List[Dict[str, Any]]) -> Tuple[str, List[Dict[str, Any]]]:
    system: List[str] = []
    turns: List[Dict[str, Any]] = []

    def push(role: str, blocks: List[Dict[str, Any]]) -> None:
        if turns and turns[-1]["role"] == role:
            turns[-1]["content"].extend(blocks)
        else:
            turns.append({"role": role, "content": list(blocks)})

    for m in messages:
        role = m.get("role")
        if role == "system":
            system.append(text_content(m.get("content")))
        elif role == "user":
            push("user", [{"type": "text", "text": text_content(m.get("content")) or " "}])
        elif role == "assistant":
            blocks: List[Dict[str, Any]] = []
            txt = text_content(m.get("content"))
            if txt:
                blocks.append({"type": "text", "text": txt})
            for c in m.get("tool_calls") or []:
                tc = ToolCall.from_openai(c)
                blocks.append({"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.arguments})
            push("assistant", blocks or [{"type": "text", "text": " "}])
        elif role == "tool":
            push("user", [{"type": "tool_result", "tool_use_id": m.get("tool_call_id") or "",
                           "content": text_content(m.get("content"))}])
    return "\n\n".join(s for s in system if s), turns


def tools_to_anthropic(tools: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    out = []
    for t in tools or []:
        fn = t.get("function") or t
        out.append({"name": fn["name"], "description": fn.get("description", ""),
                    "input_schema": fn.get("parameters") or {"type": "object", "properties": {}}})
    return out


class AnthropicProvider(ModelProvider):
    kind = "anthropic"

    def __init__(self, name: str = "anthropic", base_url: str = "https://api.anthropic.com/v1", api_key: KeySource = None,
                 key_setting: Optional[str] = "ANTHROPIC_API_KEY", transport: Optional[Transport] = None):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.key_setting = key_setting
        self.transport = transport or UrllibTransport()

    def configured(self) -> Tuple[bool, str]:
        if key_value(self._api_key):
            return True, f"key from {self.key_setting} (value never logged)"
        return False, f"no API key: set {self.key_setting} or run desk.py auth configure {self.name}"

    def _headers(self) -> Dict[str, str]:
        key = key_value(self._api_key)
        if not key:
            raise ProviderError(f"no API key for provider '{self.name}': set {self.key_setting}", kind="config")
        return {"x-api-key": key, "anthropic-version": API_VERSION, "content-type": "application/json",
                "accept": "application/json"}

    def build_body(self, req: ChatRequest, stream: bool = False) -> Dict[str, Any]:
        system, turns = to_anthropic(req.messages)
        if req.json_mode:
            system = (system + "\n\n" if system else "") + json_instruction(req.json_schema)
        body: Dict[str, Any] = {"model": req.model, "messages": turns, "max_tokens": int(req.max_tokens),
                                "temperature": req.temperature}
        if system:
            body["system"] = system
        if req.tools:
            body["tools"] = tools_to_anthropic(req.tools)
            body["tool_choice"] = _CHOICE.get(req.tool_choice, {"type": "auto"})
        if stream:
            body["stream"] = True
        return body

    def parse(self, resp: Dict[str, Any], model: str, t0: float) -> ChatResponse:
        if resp.get("type") == "error":
            err = resp.get("error") or {}
            raise ProviderError(f"{err.get('type')}: {err.get('message')}", kind="bad_response")
        content = resp.get("content")
        if not isinstance(content, list):
            raise ProviderError("malformed Messages response (no content)", kind="bad_response")
        text = "".join(b.get("text", "") for b in content if b.get("type") == "text")
        calls = [ToolCall(id=b.get("id", ""), name=b.get("name", ""), arguments=b.get("input") or {})
                 for b in content if b.get("type") == "tool_use"]
        u = resp.get("usage") or {}
        return ChatResponse(provider=self.name, model=resp.get("model") or model, text=text, tool_calls=calls,
                            finish_reason=resp.get("stop_reason"),
                            usage=Usage(int(u.get("input_tokens") or 0), int(u.get("output_tokens") or 0)),
                            latency_ms=round((time.perf_counter() - t0) * 1000, 2))

    def chat(self, req: ChatRequest) -> ChatResponse:
        t0 = time.perf_counter()
        resp = self.transport.post_json(self.base_url + "/messages", self._headers(), self.build_body(req), req.timeout)
        return self.parse(resp, req.model, t0)

    def stream(self, req: ChatRequest) -> Iterator[StreamEvent]:
        t0 = time.perf_counter()
        blocks: Dict[int, Dict[str, Any]] = {}
        text: List[str] = []
        usage, finish, model = Usage(), None, req.model
        lines = self.transport.stream_lines(self.base_url + "/messages", self._headers(),
                                            self.build_body(req, stream=True), req.timeout)
        for event, data in sse_data(lines):
            try:
                ev = json.loads(data)
            except ValueError:
                continue
            et = ev.get("type") or event
            if et == "error":
                err = ev.get("error") or {}
                raise ProviderError(f"{err.get('type')}: {err.get('message')}",
                                    kind="server", retryable=err.get("type") == "overloaded_error")
            if et == "message_start":
                msg = ev.get("message") or {}
                model = msg.get("model") or model
                usage.input_tokens = int((msg.get("usage") or {}).get("input_tokens") or 0)
            elif et == "content_block_start":
                cb = ev.get("content_block") or {}
                blocks[int(ev.get("index", 0))] = {"type": cb.get("type"), "id": cb.get("id", ""),
                                                   "name": cb.get("name", ""), "json": []}
            elif et == "content_block_delta":
                d = ev.get("delta") or {}
                slot = blocks.setdefault(int(ev.get("index", 0)), {"type": "text", "json": []})
                if d.get("type") == "text_delta":
                    text.append(d.get("text", ""))
                    yield StreamEvent(type="text", text=d.get("text", ""))
                elif d.get("type") == "input_json_delta":
                    slot["json"].append(d.get("partial_json", ""))
            elif et == "message_delta":
                finish = (ev.get("delta") or {}).get("stop_reason") or finish
                usage.output_tokens = int((ev.get("usage") or {}).get("output_tokens") or usage.output_tokens)
        calls = []
        for i in sorted(blocks):
            b = blocks[i]
            if b.get("type") != "tool_use":
                continue
            tc = ToolCall.from_openai({"id": b["id"], "function": {"name": b["name"], "arguments": "".join(b["json"]) or "{}"}})
            calls.append(tc)
            yield StreamEvent(type="tool_call", tool_call=tc)
        yield StreamEvent(type="done", response=ChatResponse(
            provider=self.name, model=model, text="".join(text), tool_calls=calls, finish_reason=finish,
            usage=usage, latency_ms=round((time.perf_counter() - t0) * 1000, 2)))

    def list_models(self, timeout: float = 10.0) -> List[str]:
        data = self.transport.get_json(self.base_url + "/models", self._headers(), timeout)
        return [m.get("id") for m in (data.get("data") or []) if isinstance(m, dict) and m.get("id")]
