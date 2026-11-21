"""Prompt-based tool calling for models without native tool support.

Many local and open-source models never emit structured tool calls. Rather than exclude them,
DESK wraps the provider: the tool catalogue and a strict reply protocol go into the system
prompt, earlier tool calls and results are rendered as text, and the model's reply is parsed
back into `ToolCall`s. The caller (agent_loop) sees the same ChatResponse shape either way;
`via="prompt_tools"` records that the orchestration adapter was used.

DESK still executes every tool itself and still refuses names it did not offer; the protocol
changes only how the model asks.

Zero external dependencies.
"""
from __future__ import annotations

import itertools
import json
from typing import Any, Dict, List, Optional, Tuple

from desk.orchestrator.providers.base import ChatRequest, ChatResponse, ModelProvider, ToolCall, text_content

_TURNS = itertools.count(1)   # unique call ids across turns and wrapper instances

PROTOCOL = """You can call tools. The tools available to you, as JSON schemas:
{catalogue}

To call one or more tools, reply with ONLY this JSON object and nothing else:
{{"tool_calls": [{{"name": "<tool name>", "arguments": {{...}}}}]}}
Tool results come back in a user message that starts with TOOL_RESULT.
When you have finished, reply with your final answer as normal text (or the JSON the task asks for),
never inside a "tool_calls" object. Use only the tools listed above."""


def _first_json_object(text: str) -> Optional[Dict[str, Any]]:
    from desk.orchestrator.http_adapter import _extract_json
    j = _extract_json(text or "")
    return j if isinstance(j, dict) else None


def render_protocol(tools: List[Dict[str, Any]]) -> str:
    cat = []
    for t in tools:
        fn = t.get("function") or t
        cat.append({"name": fn["name"], "description": fn.get("description", ""), "parameters": fn.get("parameters", {})})
    return PROTOCOL.format(catalogue=json.dumps(cat, ensure_ascii=False))


def to_prompt_messages(messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    proto = render_protocol(tools)
    placed = False
    for m in messages:
        role = m.get("role")
        if role == "system" and not placed:
            out.append({"role": "system", "content": text_content(m.get("content")) + "\n\n" + proto})
            placed = True
        elif role == "assistant" and m.get("tool_calls"):
            calls = [ToolCall.from_openai(c) for c in m["tool_calls"]]
            body = json.dumps({"tool_calls": [{"name": c.name, "arguments": c.arguments} for c in calls]}, ensure_ascii=False)
            txt = text_content(m.get("content"))
            out.append({"role": "assistant", "content": (txt + "\n" if txt else "") + body})
        elif role == "tool":
            out.append({"role": "user", "content": f"TOOL_RESULT {m.get('name') or ''} ({m.get('tool_call_id') or ''}):\n"
                                                   + text_content(m.get("content"))})
        else:
            out.append(dict(m))
    if not placed:
        out.insert(0, {"role": "system", "content": proto})
    return out


def parse_reply(text: str, turn_tag: str = "ptc") -> Tuple[str, List[ToolCall]]:
    """(final_text, tool_calls). A reply is a tool request only when it is a JSON object whose
    `tool_calls` is a list; anything else is the model's answer, returned verbatim."""
    obj = _first_json_object(text)
    if not obj or not isinstance(obj.get("tool_calls"), list):
        return text, []
    calls = []
    for i, c in enumerate(obj["tool_calls"], 1):
        if not isinstance(c, dict) or not c.get("name"):
            continue
        args = c.get("arguments", {})
        if isinstance(args, str):
            try:
                args = json.loads(args or "{}")
            except ValueError:
                args = {"__unparsed__": args}
        calls.append(ToolCall(id=f"{turn_tag}_{i}", name=str(c["name"]), arguments=args if isinstance(args, dict) else {}))
    return ("" if calls else text), calls


class PromptToolProvider(ModelProvider):
    """Wraps any provider; adds tool calling through the prompt when the request carries tools."""

    kind = "prompt_tools"

    def __init__(self, inner: ModelProvider):
        self.inner = inner
        self.name = inner.name

    def configured(self):
        return self.inner.configured()

    def list_models(self, timeout: float = 10.0):
        return self.inner.list_models(timeout)

    def chat(self, req: ChatRequest) -> ChatResponse:
        if not req.tools:
            return self.inner.chat(req)
        inner_req = ChatRequest(model=req.model, messages=to_prompt_messages(req.messages, req.tools), tools=None,
                                json_mode=False, max_tokens=req.max_tokens, temperature=req.temperature,
                                timeout=req.timeout, thinking=req.thinking)
        resp = self.inner.chat(inner_req)
        text, calls = parse_reply(resp.text, f"ptc{next(_TURNS)}")
        resp.text, resp.tool_calls, resp.via = text, calls, "prompt_tools"
        if calls:
            resp.finish_reason = "tool_calls"
        return resp
