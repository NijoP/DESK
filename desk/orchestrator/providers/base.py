"""Common model-provider contract for DESK.

DESK is the orchestrator; a model is a replaceable component that interprets requirements and
proposes. Every provider (OpenAI-compatible HTTP, Anthropic, Gemini, a fake in tests) speaks this
one contract, so no engineering code depends on a vendor.

Canonical conversation format: OpenAI-style message dicts, because `agent_loop.py` already uses
them and most endpoints accept them unchanged:

    {"role": "system" | "user" | "assistant" | "tool", "content": str,
     "tool_calls": [{"id", "type": "function", "function": {"name", "arguments": "<json>"}}],  # assistant
     "tool_call_id": str, "name": str}                                                         # tool

Adapters translate that format to and from their wire format. HTTP goes through a `Transport`
(stdlib urllib by default) so tests inject recorded fixtures and never touch the network.

Zero external dependencies.
"""
from __future__ import annotations

import json
import re
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Iterator, List, Optional, Tuple

# Statuses worth retrying with backoff: rate limit, transient server faults, overload.
RETRYABLE_STATUS = frozenset({408, 409, 425, 429, 500, 502, 503, 504, 529})

_SECRET_RX = re.compile(r"(nvapi-|sk-ant-|sk-|xai-|AIza|ghp_)[A-Za-z0-9_\-]{6,}")


def redact(text: str) -> str:
    """Mask anything shaped like an API key. Applied to every error message a provider returns."""
    return _SECRET_RX.sub(lambda m: m.group(1) + "[REDACTED]", text or "")


class ProviderError(Exception):
    """A failed model call. `retryable` drives the retry policy; `kind` is a short machine label:
    auth, rate_limit, server, timeout, network, bad_request, bad_response, unsupported, config."""

    def __init__(self, message: str, kind: str = "server", retryable: bool = False,
                 status: Optional[int] = None, retry_after: Optional[float] = None):
        super().__init__(redact(message))
        self.kind = kind
        self.retryable = retryable
        self.status = status
        self.retry_after = retry_after


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    provider_meta: Dict[str, Any] = field(default_factory=dict)  # opaque round-trip data (e.g. Gemini thoughtSignature)

    def to_openai(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"id": self.id, "type": "function",
                             "function": {"name": self.name, "arguments": json.dumps(self.arguments, ensure_ascii=False)}}
        if self.provider_meta:
            d["provider_meta"] = dict(self.provider_meta)
        return d

    @staticmethod
    def from_openai(d: Dict[str, Any]) -> "ToolCall":
        fn = d.get("function") or {}
        raw = fn.get("arguments", {})
        if isinstance(raw, str):
            try:
                raw = json.loads(raw or "{}")
            except ValueError:
                raw = {"__unparsed__": raw}
        return ToolCall(id=str(d.get("id") or ""), name=str(fn.get("name") or ""),
                        arguments=raw if isinstance(raw, dict) else {"value": raw},
                        provider_meta=dict(d.get("provider_meta") or {}))


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    estimated: bool = False   # True when the provider reported nothing and DESK estimated

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def to_dict(self) -> Dict[str, Any]:
        return {"prompt_tokens": self.input_tokens, "completion_tokens": self.output_tokens,
                "total_tokens": self.total_tokens, "estimated": self.estimated}


@dataclass
class ChatRequest:
    model: str
    messages: List[Dict[str, Any]]
    tools: Optional[List[Dict[str, Any]]] = None   # OpenAI function-tool schemas
    tool_choice: str = "auto"
    json_mode: bool = False                         # ask for a single JSON object
    json_schema: Optional[Dict[str, Any]] = None
    max_tokens: int = 2048
    temperature: float = 0.0
    timeout: float = 60.0
    thinking: Optional[str] = None                  # off | low | medium | high | None (provider default)


@dataclass
class ChatResponse:
    provider: str
    model: str
    text: str = ""
    tool_calls: List[ToolCall] = field(default_factory=list)
    finish_reason: Optional[str] = None
    usage: Usage = field(default_factory=Usage)
    latency_ms: float = 0.0
    via: str = "native"                             # native | prompt_tools (orchestration adapter)

    def message(self) -> Dict[str, Any]:
        """The assistant turn in canonical (OpenAI-style) form."""
        m: Dict[str, Any] = {"role": "assistant", "content": self.text}
        if self.tool_calls:
            m["tool_calls"] = [c.to_openai() for c in self.tool_calls]
        return m

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["usage"] = self.usage.to_dict()
        return d


@dataclass(frozen=True)
class ModelRoute:
    """One concrete (provider, model) pair. Written "provider:model" in config and policy data;
    only the first colon separates, so local ids such as "ollama:qwen3:8b" survive."""
    provider: str
    model: str

    def __str__(self) -> str:
        return f"{self.provider}:{self.model}"


@dataclass
class StreamEvent:
    type: str                                       # text | tool_call | done
    text: str = ""
    tool_call: Optional[ToolCall] = None
    response: Optional[ChatResponse] = None         # set on "done": the assembled response


# ---------------------------------------------------------------------------------------------- transport
class Transport:
    """HTTP seam. `post_json`/`get_json` return the decoded JSON body; `stream_lines` yields raw
    response lines. All raise ProviderError. Tests substitute a recorded-fixture transport."""

    def post_json(self, url: str, headers: Dict[str, str], body: Dict[str, Any], timeout: float) -> Dict[str, Any]:
        raise NotImplementedError

    def get_json(self, url: str, headers: Dict[str, str], timeout: float) -> Dict[str, Any]:
        raise NotImplementedError

    def stream_lines(self, url: str, headers: Dict[str, str], body: Dict[str, Any], timeout: float) -> Iterator[str]:
        raise NotImplementedError


def _http_error(e: urllib.error.HTTPError) -> ProviderError:
    detail = ""
    try:
        detail = e.read().decode("utf-8", "replace")[:300]
    except Exception:
        pass
    retry_after = None
    try:
        ra = e.headers.get("Retry-After") if e.headers else None
        retry_after = float(ra) if ra else None
    except (TypeError, ValueError):
        retry_after = None
    return error_for_status(e.code, detail, retry_after)


def error_for_status(status: int, detail: str = "", retry_after: Optional[float] = None) -> ProviderError:
    kind = ("auth" if status in (401, 403) else "rate_limit" if status == 429
            else "server" if status >= 500 else "bad_request")
    return ProviderError(f"HTTP {status}: {detail}", kind=kind, retryable=status in RETRYABLE_STATUS,
                         status=status, retry_after=retry_after)


def _net_error(e: BaseException, timeout: float) -> ProviderError:
    if isinstance(e, (socket.timeout, TimeoutError)) or "timed out" in str(e).lower():
        return ProviderError(f"timed out after {timeout:g} s", kind="timeout", retryable=True)
    return ProviderError(f"{type(e).__name__}: {str(e)[:200]}", kind="network", retryable=True)


class UrllibTransport(Transport):
    """Default transport: stdlib urllib, explicit timeout on every request."""

    @staticmethod
    def _request(url: str, headers: Dict[str, str], body: Optional[Dict[str, Any]]) -> urllib.request.Request:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        return urllib.request.Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")

    @staticmethod
    def _open_json(req: urllib.request.Request, timeout: float) -> Dict[str, Any]:
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            raise _http_error(e)
        except Exception as e:
            raise _net_error(e, timeout)
        try:
            return json.loads(raw)
        except ValueError:
            raise ProviderError("response is not JSON: " + raw[:120], kind="bad_response")

    def post_json(self, url, headers, body, timeout):
        return self._open_json(self._request(url, headers, body), timeout)

    def get_json(self, url, headers, timeout):
        return self._open_json(self._request(url, headers, None), timeout)

    def stream_lines(self, url, headers, body, timeout):
        try:
            r = urllib.request.urlopen(self._request(url, headers, body), timeout=timeout)
        except urllib.error.HTTPError as e:
            raise _http_error(e)
        except Exception as e:
            raise _net_error(e, timeout)
        try:
            for raw in r:
                yield raw.decode("utf-8", "replace").rstrip("\r\n")
        except Exception as e:
            raise _net_error(e, timeout)
        finally:
            r.close()


def sse_data(lines) -> Iterator[Tuple[str, str]]:
    """Parse server-sent events into (event, data) pairs; `data: [DONE]` ends the stream."""
    event, buf = "", []
    for line in lines:
        if line == "":
            if buf:
                data = "\n".join(buf)
                if data.strip() == "[DONE]":
                    return
                yield event, data
            event, buf = "", []
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            buf.append(line[5:].lstrip())
    if buf:
        data = "\n".join(buf)
        if data.strip() != "[DONE]":
            yield event, data


# ---------------------------------------------------------------------------------------------- provider
class ModelProvider:
    """Base class every provider implements. `chat` is required; `stream` defaults to one chunk."""

    name: str = "base"
    kind: str = "base"

    def configured(self) -> Tuple[bool, str]:
        """(ready, reason). Ready means credentials (if any are needed) are present. No network."""
        return True, "no credentials required"

    def list_models(self, timeout: float = 10.0) -> List[str]:
        """Model discovery. Network call for HTTP providers; raises ProviderError."""
        return []

    def chat(self, req: ChatRequest) -> ChatResponse:
        raise NotImplementedError

    def stream(self, req: ChatRequest) -> Iterator[StreamEvent]:
        resp = self.chat(req)
        if resp.text:
            yield StreamEvent(type="text", text=resp.text)
        for c in resp.tool_calls:
            yield StreamEvent(type="tool_call", tool_call=c)
        yield StreamEvent(type="done", response=resp)


def estimate_tokens(messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None) -> int:
    """Rough prompt size (4 characters per token, rounded up). Used only for context-window
    checks and when a provider reports no usage; such usage is marked estimated."""
    n = len(json.dumps(messages, ensure_ascii=False))
    if tools:
        n += len(json.dumps(tools, ensure_ascii=False))
    return n // 4 + 1


def json_instruction(schema: Optional[Dict[str, Any]]) -> str:
    s = "Respond with a single JSON object and nothing else."
    if schema:
        s += " It must conform to this JSON schema:\n" + json.dumps(schema)
    return s


def text_content(content: Any) -> str:
    """Flatten OpenAI content (a string or a list of parts) to text; image parts are dropped."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text")
    return str(content)
