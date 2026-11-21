"""Google Gemini API (generativelanguage v1beta) provider, stdlib urllib, no SDK.

Translation from DESK's canonical OpenAI-style conversation:
  * system messages      -> `systemInstruction`
  * assistant            -> role "model"; tool_calls -> `functionCall` parts (thoughtSignature echoed back
                            from ToolCall.provider_meta, which Gemini requires on multi-turn function calls)
  * tool messages        -> `functionResponse` parts in a user turn (adjacent same-role turns merged)
  * OpenAI tool schemas  -> `functionDeclarations` (JSON-schema keys Gemini rejects are stripped)
Gemini function calls may carry no ids; DESK assigns `gemini_call_<n>` ids and maps them back by name.

The key goes in the `x-goog-api-key` header, never in the URL, so it cannot leak into logs.

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

_MODE = {"auto": "AUTO", "required": "ANY", "any": "ANY", "none": "NONE"}
_DROP_SCHEMA_KEYS = {"additionalProperties", "$schema", "$id", "default", "examples"}


def _schema(s: Any) -> Any:
    if isinstance(s, dict):
        return {k: _schema(v) for k, v in s.items() if k not in _DROP_SCHEMA_KEYS}
    if isinstance(s, list):
        return [_schema(v) for v in s]
    return s


def to_gemini(messages: List[Dict[str, Any]]) -> Tuple[str, List[Dict[str, Any]]]:
    system: List[str] = []
    contents: List[Dict[str, Any]] = []
    names_by_id: Dict[str, str] = {}

    def push(role: str, parts: List[Dict[str, Any]]) -> None:
        if contents and contents[-1]["role"] == role:
            contents[-1]["parts"].extend(parts)
        else:
            contents.append({"role": role, "parts": list(parts)})

    for m in messages:
        role = m.get("role")
        if role == "system":
            system.append(text_content(m.get("content")))
        elif role == "user":
            push("user", [{"text": text_content(m.get("content")) or " "}])
        elif role == "assistant":
            parts: List[Dict[str, Any]] = []
            txt = text_content(m.get("content"))
            if txt:
                parts.append({"text": txt})
            for c in m.get("tool_calls") or []:
                tc = ToolCall.from_openai(c)
                names_by_id[tc.id] = tc.name
                part: Dict[str, Any] = {"functionCall": {"name": tc.name, "args": tc.arguments}}
                if tc.provider_meta.get("thoughtSignature"):
                    part["thoughtSignature"] = tc.provider_meta["thoughtSignature"]
                parts.append(part)
            push("model", parts or [{"text": " "}])
        elif role == "tool":
            raw = text_content(m.get("content"))
            try:
                result = json.loads(raw)
            except ValueError:
                result = raw
            name = m.get("name") or names_by_id.get(m.get("tool_call_id") or "", "")
            push("user", [{"functionResponse": {"name": name, "response": {"result": result}}}])
    return "\n\n".join(s for s in system if s), contents


def tools_to_gemini(tools: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    decls = []
    for t in tools or []:
        fn = t.get("function") or t
        d = {"name": fn["name"], "description": fn.get("description", "")}
        if fn.get("parameters"):
            d["parameters"] = _schema(fn["parameters"])
        decls.append(d)
    return [{"functionDeclarations": decls}] if decls else []


class GeminiProvider(ModelProvider):
    kind = "gemini"

    def __init__(self, name: str = "gemini", base_url: str = "https://generativelanguage.googleapis.com/v1beta",
                 api_key: KeySource = None, key_setting: Optional[str] = "GEMINI_API_KEY",
                 transport: Optional[Transport] = None):
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
        return {"x-goog-api-key": key, "Content-Type": "application/json", "Accept": "application/json"}

    @staticmethod
    def _model_path(model: str) -> str:
        return model[len("models/"):] if model.startswith("models/") else model

    def build_body(self, req: ChatRequest) -> Dict[str, Any]:
        system, contents = to_gemini(req.messages)
        gen: Dict[str, Any] = {"temperature": req.temperature, "maxOutputTokens": int(req.max_tokens)}
        if req.json_mode:
            gen["responseMimeType"] = "application/json"
            if req.json_schema:
                system = (system + "\n\n" if system else "") + json_instruction(req.json_schema)
        body: Dict[str, Any] = {"contents": contents, "generationConfig": gen}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if req.tools:
            body["tools"] = tools_to_gemini(req.tools)
            body["toolConfig"] = {"functionCallingConfig": {"mode": _MODE.get(req.tool_choice, "AUTO")}}
        return body

    @staticmethod
    def _absorb(resp: Dict[str, Any], state: Dict[str, Any]) -> List[StreamEvent]:
        """Fold one GenerateContentResponse (whole or streamed chunk) into `state`; return new events."""
        events: List[StreamEvent] = []
        fb = resp.get("promptFeedback") or {}
        if fb.get("blockReason"):
            raise ProviderError(f"prompt blocked by provider: {fb['blockReason']}", kind="bad_request")
        um = resp.get("usageMetadata") or {}
        if um:
            state["usage"] = Usage(int(um.get("promptTokenCount") or 0), int(um.get("candidatesTokenCount") or 0))
        state["model"] = resp.get("modelVersion") or state["model"]
        for cand in (resp.get("candidates") or [])[:1]:
            state["finish"] = cand.get("finishReason") or state["finish"]
            for part in (cand.get("content") or {}).get("parts") or []:
                if part.get("thought"):
                    continue
                if part.get("text"):
                    state["text"].append(part["text"])
                    events.append(StreamEvent(type="text", text=part["text"]))
                fc = part.get("functionCall")
                if fc:
                    meta = {"thoughtSignature": part["thoughtSignature"]} if part.get("thoughtSignature") else {}
                    tc = ToolCall(id=fc.get("id") or f"gemini_call_{len(state['calls']) + 1}", name=fc.get("name", ""),
                                  arguments=fc.get("args") or {}, provider_meta=meta)
                    state["calls"].append(tc)
                    events.append(StreamEvent(type="tool_call", tool_call=tc))
        return events

    @staticmethod
    def _new_state(model: str) -> Dict[str, Any]:
        return {"text": [], "calls": [], "usage": Usage(), "finish": None, "model": model}

    def _response(self, state: Dict[str, Any], t0: float) -> ChatResponse:
        return ChatResponse(provider=self.name, model=state["model"], text="".join(state["text"]), tool_calls=state["calls"],
                            finish_reason=state["finish"], usage=state["usage"],
                            latency_ms=round((time.perf_counter() - t0) * 1000, 2))

    def chat(self, req: ChatRequest) -> ChatResponse:
        t0 = time.perf_counter()
        url = f"{self.base_url}/models/{self._model_path(req.model)}:generateContent"
        resp = self.transport.post_json(url, self._headers(), self.build_body(req), req.timeout)
        if not isinstance(resp, dict) or ("candidates" not in resp and "promptFeedback" not in resp):
            raise ProviderError("malformed generateContent response (no candidates)", kind="bad_response")
        state = self._new_state(req.model)
        self._absorb(resp, state)
        return self._response(state, t0)

    def stream(self, req: ChatRequest) -> Iterator[StreamEvent]:
        t0 = time.perf_counter()
        url = f"{self.base_url}/models/{self._model_path(req.model)}:streamGenerateContent?alt=sse"
        state = self._new_state(req.model)
        for _event, data in sse_data(self.transport.stream_lines(url, self._headers(), self.build_body(req), req.timeout)):
            try:
                chunk = json.loads(data)
            except ValueError:
                continue
            for ev in self._absorb(chunk, state):
                yield ev
        yield StreamEvent(type="done", response=self._response(state, t0))

    def list_models(self, timeout: float = 10.0) -> List[str]:
        data = self.transport.get_json(self.base_url + "/models", self._headers(), timeout)
        out = []
        for m in data.get("models") or []:
            if not isinstance(m, dict) or not m.get("name"):
                continue
            methods = m.get("supportedGenerationMethods")
            if methods and "generateContent" not in methods:
                continue
            out.append(self._model_path(m["name"]))
        return out
