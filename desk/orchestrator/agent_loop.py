"""Tool-calling loop for OpenAI-compatible providers (NVIDIA NIM: Nemotron 3 Ultra / 3.5 family).

Measured 2026-11-12 on integrate.api.nvidia.com: with `tools` + `tool_choice: auto` and thinking
off (`chat_template_kwargs.enable_thinking=false`), nemotron-3-ultra-550b-a55b and
nemotron-3.5-lightning-30b-a3b return OpenAI-style `tool_calls` in about 1 s and call
`read_schematic` before deciding anything. NVIDIA's Nemotron 3 technical report describes
post-training with SFT and RL on multi-step tool use, structured output and instruction
following; the models follow explicit, short tool contracts well and do not need prose about
the ECAD API. This loop therefore gives the model DESK's deterministic tools and nothing else.

Rules enforced here, not by the prompt alone:
* every tool call is executed by DESK code (`tools_manifest.dispatch`); the model never emits JavaScript;
* mutations are impossible unless the loop is started with allow_mutation=True;
* bounded turns, bounded tool calls per turn, bounded wall clock;
* a redacted trace of every turn is written to <project>/state/agent_trace.jsonl.

Zero external dependencies.
"""
from __future__ import annotations
import json
import os
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

from desk.orchestrator.tools_manifest import tool_schemas, dispatch

DEFAULT_MODEL = "nvidia/nemotron-3-ultra-550b-a55b"

SYSTEM_PROMPT = """You are DESK's schematic and PCB agent working inside EasyEDA Pro through DESK's tools.
Facts about your environment:
- The EasyEDA API bridge SUPPORTS READS. read_schematic returns every component, uuid and pin with absolute coordinates and its net. Never say reads are unavailable without calling it.
- You never write EasyEDA JavaScript and never guess coordinates. Name pins as REF.PIN (e.g. U1.3, C2.1); plan_wires resolves coordinates and returns the exact wires DESK will create.
- Browser automation and manual UI work are not options. If a tool returns an error, report the error text and stop; do not invent a workaround.
- Mutations (wire_net, build, route) run only when the operator allowed them for this session; otherwise return the plan and ask for approval.
Working method:
1. read_schematic (or list_schematic_nets) first. 2. For each net, plan_wires with the pins. 3. If allowed, wire_net; then re-check the nets. 4. Report: nets wired, pins verified, pins refused with reasons, and what the operator must decide.
Answer with a short structured summary. Do not repeat tool output verbatim."""


@dataclass
class AgentRun:
    model: str
    turns: int
    tool_calls: int
    elapsed_s: float
    final_text: str
    final_json: Optional[Dict[str, Any]]
    stopped_reason: str
    trace_path: Optional[str]
    usage: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _redact(obj: Any) -> Any:
    s = json.dumps(obj, ensure_ascii=False)
    import re
    s = re.sub(r"(nvapi-|sk-|ghp_)[A-Za-z0-9_\-]{6,}", r"\1[REDACTED]", s)
    return json.loads(s)


def run_agent(task: str, project: Optional[str] = None, model: Optional[str] = None, adapter: Any = None,
              allow_mutation: bool = False, max_turns: int = 12, max_tool_calls_per_turn: int = 6,
              budget_sec: float = 600.0, thinking: Optional[str] = "off", window_id: Optional[str] = None,
              extra_system: str = "") -> AgentRun:
    from desk.orchestrator.http_adapter import OpenAICompatAdapter
    adapter = adapter or OpenAICompatAdapter("nvidia")
    from desk import config as deskcfg
    model = model or deskcfg.get("DESK_AGENT_MODEL") or DEFAULT_MODEL
    ctx = {"project": project, "allow_mutation": allow_mutation, "window_id": window_id}
    system = SYSTEM_PROMPT + (f"\nProject directory: {project}" if project else "") + (f"\n{extra_system}" if extra_system else "")
    messages: List[Dict[str, Any]] = [{"role": "system", "content": system}, {"role": "user", "content": task}]
    tools = tool_schemas(allow_mutation)
    trace_path = os.path.join(project, "state", "agent_trace.jsonl") if project else None
    if trace_path:
        os.makedirs(os.path.dirname(trace_path), exist_ok=True)

    def trace(rec: Dict[str, Any]) -> None:
        if not trace_path:
            return
        try:
            with open(trace_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(_redact({"ts": time.time(), **rec}), ensure_ascii=False) + "\n")
        except Exception:
            pass

    t0 = time.time()
    n_calls = 0
    usage_total: Dict[str, int] = {}
    stopped = "max_turns"
    final_text, final_json = "", None
    for turn in range(1, max_turns + 1):
        if time.time() - t0 > budget_sec:
            stopped = "budget"
            break
        resp = adapter.chat_completion(messages, model=model, tools=tools, tool_choice="auto", thinking=thinking,
                                       timeout=min(180.0, max(30.0, budget_sec - (time.time() - t0))))
        if "error" in resp:
            stopped = f"provider_error: {resp['error']}"
            trace({"turn": turn, "error": resp["error"]})
            break
        msg = resp["message"]
        for k, v in (resp.get("usage") or {}).items():
            if isinstance(v, (int, float)):
                usage_total[k] = usage_total.get(k, 0) + int(v)
        assistant = {"role": "assistant", "content": msg.get("content") or ""}
        calls = msg.get("tool_calls") or []
        if calls:
            assistant["tool_calls"] = calls
        messages.append(assistant)
        trace({"turn": turn, "assistant": {"content": (msg.get("content") or "")[:2000], "tool_calls": [c.get("function", {}).get("name") for c in calls]}})
        if not calls:
            final_text = msg.get("content") or ""
            try:
                from desk.orchestrator.http_adapter import _extract_json
                j = _extract_json(final_text)
                final_json = j if isinstance(j, dict) else None
            except Exception:
                final_json = None
            stopped = "final"
            break
        for call in calls[:max_tool_calls_per_turn]:
            fn = call.get("function", {})
            name, arguments = fn.get("name", ""), fn.get("arguments", "{}")
            result = dispatch(name, arguments, ctx)
            n_calls += 1
            payload = json.dumps(result, ensure_ascii=False)
            if len(payload) > 60000:
                payload = payload[:60000] + "... [truncated by DESK]"
            messages.append({"role": "tool", "tool_call_id": call.get("id") or f"call_{turn}_{n_calls}", "name": name, "content": payload})
            trace({"turn": turn, "tool": name, "arguments": arguments if isinstance(arguments, str) else json.dumps(arguments),
                   "result_preview": payload[:1500], "error": result.get("error") if isinstance(result, dict) else None})
        if len(calls) > max_tool_calls_per_turn:
            messages.append({"role": "user", "content": f"Only the first {max_tool_calls_per_turn} tool calls were executed; continue."})
    run = AgentRun(model=model, turns=turn if 'turn' in dir() else 0, tool_calls=n_calls, elapsed_s=round(time.time() - t0, 1),
                   final_text=final_text, final_json=final_json, stopped_reason=stopped, trace_path=trace_path, usage=usage_total)
    trace({"run": run.to_dict()})
    return run
