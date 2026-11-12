"""DESK tools exposed to tool-calling models (OpenAI function format) with deterministic handlers.

Principle: the model reasons and chooses; DESK's deterministic functions read the board, compute
coordinates, size copper and verify. A model never writes EasyEDA JavaScript, never guesses
coordinates and never gets a mutation unless the loop was started with `allow_mutation=True`.

Zero external dependencies.
"""
from __future__ import annotations
import json
import os
from typing import Any, Callable, Dict, List, Optional

ToolHandler = Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]]

TOOLS: List[Dict[str, Any]] = [
    {"type": "function", "function": {
        "name": "read_schematic",
        "description": "READ-ONLY. Return every component on the active EasyEDA schematic: designator, uuid, position, and each pin's number, name, absolute x/y, rotation and current net. Call this before any wiring decision. Saves state/sch_dump.json.",
        "parameters": {"type": "object", "properties": {"project": {"type": "string", "description": "project directory, e.g. projects/MYBOARD"}}, "required": ["project"]}}},
    {"type": "function", "function": {
        "name": "list_schematic_nets",
        "description": "READ-ONLY. Net names present on the schematic and the pins on each net (from the last read_schematic or a fresh read).",
        "parameters": {"type": "object", "properties": {"project": {"type": "string"}}, "required": ["project"]}}},
    {"type": "function", "function": {
        "name": "plan_wires",
        "description": "Deterministic, no mutation. Resolve pins named as REF.PIN against the sheet and return the exact stub wires and net labels DESK would create for `net`. Refuses unknown pins, no-connect pins and pins already on another net.",
        "parameters": {"type": "object", "properties": {"project": {"type": "string"}, "net": {"type": "string"},
                                                        "pins": {"type": "array", "items": {"type": "string"}, "description": "e.g. [\"U1.3\", \"C2.1\"]"}},
                       "required": ["project", "net", "pins"]}}},
    {"type": "function", "function": {
        "name": "wire_net",
        "description": "MUTATION (only when the session allows it). Create the planned stub wires and net labels on the live sheet under the single-writer lock, then read back and report which pins now carry the net.",
        "parameters": {"type": "object", "properties": {"project": {"type": "string"}, "net": {"type": "string"},
                                                        "pins": {"type": "array", "items": {"type": "string"}}},
                       "required": ["project", "net", "pins"]}}},
    {"type": "function", "function": {
        "name": "read_pcb",
        "description": "READ-ONLY. Return the PCB components with pads (absolute offsets, nets, layers) from state/pcb_dump.json (run tools/pcb_dump.py first when stale).",
        "parameters": {"type": "object", "properties": {"project": {"type": "string"}}, "required": ["project"]}}},
    {"type": "function", "function": {
        "name": "dense_board_analysis",
        "description": "Offline. Congestion hotspots with measured causes, corridors and the net priority order for the PCB in state/pcb_dump.json.",
        "parameters": {"type": "object", "properties": {"project": {"type": "string"}}, "required": ["project"]}}},
    {"type": "function", "function": {
        "name": "doctor",
        "description": "READ-ONLY. Environment checks: bridge, Java, Freerouting, model CLIs, project binding; each failure has a fix.",
        "parameters": {"type": "object", "properties": {"project": {"type": "string"}}, "required": []}}},
    {"type": "function", "function": {
        "name": "classify_requirements",
        "description": "READ-ONLY, deterministic. Classify client requirements (text or a JSON object of declared values) into a primary PCB archetype, secondary archetypes, engineering overlays, required component families, missing information and conflicts. Call this before proposing any design.",
        "parameters": {"type": "object", "properties": {"requirements": {"type": "string", "description": "requirement text, or a JSON object as a string"}}, "required": ["requirements"]}}},
    {"type": "function", "function": {
        "name": "domain_rules",
        "description": "READ-ONLY. The engineering rules DESK applies for an archetype (with overlays): which are ENFORCED by a DESK subsystem, which are ADVISORY and which are UNSUPPORTED, with their standards references. Also returns a compact context block.",
        "parameters": {"type": "object", "properties": {"archetype_id": {"type": "string"}, "overlays": {"type": "array", "items": {"type": "string"}}}, "required": ["archetype_id"]}}},
    {"type": "function", "function": {
        "name": "run_desk_tool",
        "description": "Run one of DESK's own CLI tools (verify, lint, erc, pcb_check, route --dry) for the project and return its output. Mutating tools (build, clear_block, route, pcb_place) are refused unless the session allows mutation.",
        "parameters": {"type": "object", "properties": {"project": {"type": "string"}, "tool": {"type": "string", "enum": ["verify", "lint", "erc", "pcb_check", "route_dry", "bom", "ping"]},
                                                        "args": {"type": "array", "items": {"type": "string"}}},
                       "required": ["project", "tool"]}}},
]

MUTATING = {"wire_net"}
MUTATING_TOOLS_CLI = {"build", "clear_block", "route", "pcb_place", "release"}


def _h_read_schematic(args, ctx):
    from desk.schematic_io import read_schematic
    d = read_schematic(args["project"], ctx.get("window_id"))
    # keep the payload compact for the model: coordinates stay, netlist text is dropped
    return {"project": d["project"], "part_count": d["part_count"], "pin_count": d["pin_count"], "nets": d["nets"],
            "parts": [{"ref": p["ref"], "uuid": p.get("uuid"), "dev": p.get("dev"), "x": p["x"], "y": p["y"], "rot": p.get("rot"),
                       "pins": [{"num": q["num"], "name": q.get("name"), "x": q["x"], "y": q["y"], "rot": q.get("rot"), "net": q.get("net"), "nc": q.get("nc")}
                                for q in p.get("pins", [])]} for p in d["parts"]]}


def _h_list_nets(args, ctx):
    from desk.schematic_io import read_schematic
    path = os.path.join(args["project"], "state", "sch_dump.json")
    d = None
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            d = None
    if d is None:
        d = read_schematic(args["project"], ctx.get("window_id"))
    nets: Dict[str, List[str]] = {}
    unconnected: List[str] = []
    for part in d.get("parts", []):
        for p in part.get("pins", []):
            key = f"{part['ref']}.{p['num']}"
            if p.get("net"):
                nets.setdefault(p["net"], []).append(key)
            elif not p.get("nc"):
                unconnected.append(key)
    return {"nets": nets, "unconnected_pins": unconnected, "source": "state/sch_dump.json" if os.path.exists(path) else "live"}


def _h_plan_wires(args, ctx):
    from desk.schematic_io import wire_net
    return wire_net(args["project"], args["net"], list(args.get("pins") or []), ctx.get("window_id"), apply=False)


def _h_wire_net(args, ctx):
    if not ctx.get("allow_mutation"):
        return {"error": "mutation not allowed in this session; call plan_wires and ask the operator to approve, or rerun with --allow-mutation"}
    from desk.schematic_io import wire_net
    from desk import ops
    approval = ops.record_approval(args["project"], "wire_net", args["net"], granted_by="operator",
                                   how="desk.py agent --allow-mutation (model requested wire_net)", reason=str(args.get("reason") or "")[:200])
    return wire_net(args["project"], args["net"], list(args.get("pins") or []), ctx.get("window_id"), apply=True, approval=approval)


def _h_read_pcb(args, ctx):
    path = os.path.join(args["project"], "state", "pcb_dump.json")
    if not os.path.exists(path):
        return {"error": f"{path} missing; run python tools/pcb_dump.py {args['project']} (mutation-free readback)"}
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    return {"components": len(d), "parts": {r: {"x": c.get("x"), "y": c.get("y"), "rot": c.get("rot"), "layer": c.get("layer"), "fp": c.get("fp"),
                                               "pads": [{"num": p.get("num"), "dx": p.get("dx"), "dy": p.get("dy"), "net": p.get("net"), "layer": p.get("layer")} for p in c.get("pads", [])]}
                                           for r, c in d.items() if isinstance(c, dict)}}


def _h_dense(args, ctx):
    from desk.routing.density import DensePCBIntelligence, dump_to_board_mm
    from desk.routing.fixtures import plane_layers_from_planes
    proj = args["project"]
    with open(os.path.join(proj, "state", "pcb_dump.json"), encoding="utf-8") as f:
        dump = json.load(f)
    plan_path = os.path.join(proj, "placement.json")
    plan = {}
    if os.path.exists(plan_path):
        with open(plan_path, encoding="utf-8") as f:
            plan = json.load(f)
    board = tuple(plan.get("board_mm")) if plan.get("board_mm") else dump_to_board_mm(dump)[0]
    origin = tuple(plan.get("origin_mm", (0.0, 0.0)))
    stack = ["Top", "Inner1", "Inner2", "Bottom"] if plan.get("layers") == 4 else ["Top", "Bottom"]
    rep = DensePCBIntelligence(dump, board, origin, stackup=stack, plane_layers=plane_layers_from_planes(plan.get("planes", []), stack),
                               keepouts_mm=plan.get("route_keepouts") or plan.get("keepouts")).analyze()
    return rep.to_mission_control()


def _h_doctor(args, ctx):
    from desk import doctor
    return {"checks": [c.to_dict() for c in doctor.run(args.get("project"))]}


def _h_run_tool(args, ctx):
    import subprocess, sys
    tool = args["tool"]
    mapping = {"verify": ["tools/verify.py"], "lint": ["tools/lint.py"], "erc": ["tools/erc.py"], "pcb_check": ["tools/pcb_check.py"],
               "route_dry": ["tools/route.py", "--dry"], "bom": ["tools/bom.py"], "ping": ["tools/ping.py"]}
    if tool not in mapping:
        return {"error": f"unknown tool {tool}"}
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    script = os.path.join(base, mapping[tool][0])
    extra = [a for a in (args.get("args") or []) if isinstance(a, str) and not a.startswith("-") or a in ("--json", "--gate", "--dry")]
    cmd = [sys.executable, script, args["project"]] + mapping[tool][1:] + extra
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600, cwd=base)
        return {"tool": tool, "returncode": p.returncode, "stdout": p.stdout[-6000:], "stderr": p.stderr[-2000:]}
    except subprocess.TimeoutExpired:
        return {"error": f"{tool} timed out after 600 s"}


def _h_classify(args, ctx):
    from desk.domain_intelligence import api as dapi
    src = args.get("requirements", "")
    try:
        parsed = json.loads(src) if isinstance(src, str) and src.strip().startswith("{") else src
    except Exception:
        parsed = src
    r = dapi.classify(parsed)
    d = r.to_dict()
    d["candidates"] = d["candidates"][:5]
    return d


def _h_domain_rules(args, ctx):
    from desk.domain_intelligence import api as dapi
    d = dapi.rules_for(args["archetype_id"], overlays=args.get("overlays"))
    d["context"] = dapi.agent_context(args["archetype_id"], overlays=args.get("overlays"))
    return d


HANDLERS: Dict[str, ToolHandler] = {
    "classify_requirements": _h_classify,
    "domain_rules": _h_domain_rules,
    "read_schematic": _h_read_schematic,
    "list_schematic_nets": _h_list_nets,
    "plan_wires": _h_plan_wires,
    "wire_net": _h_wire_net,
    "read_pcb": _h_read_pcb,
    "dense_board_analysis": _h_dense,
    "doctor": _h_doctor,
    "run_desk_tool": _h_run_tool,
}


def tool_schemas(allow_mutation: bool = False) -> List[Dict[str, Any]]:
    return [t for t in TOOLS if allow_mutation or t["function"]["name"] not in MUTATING]


def dispatch(name: str, arguments: Any, ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Run a tool by name. Never raises: errors come back as {"error": ...} so the model can recover."""
    h = HANDLERS.get(name)
    if not h:
        return {"error": f"unknown tool '{name}'; available: {sorted(HANDLERS)}"}
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments or "{}")
        except Exception as e:
            return {"error": f"arguments are not valid JSON: {e}"}
    if not isinstance(arguments, dict):
        return {"error": "arguments must be a JSON object"}
    if "project" in arguments and not arguments["project"]:
        arguments["project"] = ctx.get("project")
    if "project" not in arguments and ctx.get("project") and name != "doctor":
        arguments["project"] = ctx["project"]
    try:
        return h(arguments, ctx)
    except BaseException as e:   # SystemExit from bridge helpers included
        return {"error": f"{type(e).__name__}: {str(e)[:400]}"}
