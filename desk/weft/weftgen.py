"""Generate the DESK Weft node library from the node contracts.

Each DESK node is one Weft file holding one typed Group (Weft's unit of reuse, included with
`@include("__catalog/desk/<file>.weft")`). The group posts its inputs to the DESK node service with Weft's
stock HttpRequest node and checks the answer against the node's envelope type with Cast. An error answer has
no `outputs`, so the Cast fails and the run fails: a failed engineering call can never flow on as a success.

Native Rust nodes are deliberately not used yet: they cannot be compiled or tested without a Linux Weft
runtime, and the group form needs no unverified Rust.

The files under integrations/weft/nodes/desk/ are generated: edit desk/weft/contracts.py and run
`python desk.py weft gen`. tests/test_weft_contracts.py fails when they drift.
"""
from __future__ import annotations

import os
from typing import Dict, List

from desk.weft import contracts as C

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NODES_DIR = os.path.join(REPO, "integrations", "weft", "nodes", "desk")


def render(c: C.NodeContract) -> str:
    # Group ports take no `?` (the compiler refuses it): optionality is expressed on the JsonObject key inside.
    ins = ["service: String"] + [f"{f.name}: {f.weft_type}" for f in c.inputs]
    envelope = f"{c.node_id}Envelope"   # a named type has one body per program, so each node names its own
    outs = ["passed: Boolean", "blocking: List[String]", "evidence: List[String]"] + [f"{f.name}: {f.weft_type}" for f in c.outputs]
    out_type = "{ " + ", ".join([f"{f.name}: {f.weft_type}" for f in c.outputs] + [".."]) + " }" if c.outputs else "JsonDict"
    state = "" if c.status == "available" else f" [UNAVAILABLE, fails closed: {c.unavailable_reason}]"
    lines: List[str] = [
        f"# {c.node_id} {c.version}: {c.summary}{state}",
        f"Group({', '.join(ins)}) -> ({', '.join(outs)}) {{",
        f"  # Generated from desk/weft/contracts.py. Engine: {c.engine}",
        f"  type {envelope} = {{",
        "    node: String,",
        "    version: String,",
        "    ok: Boolean,",
        "    passed: Boolean,",
        f"    outputs: {out_type},",
        "    blockingIssues: List[String],",
        "    evidence: List[String],",
        "    ..",
        "  }",
        "  url = Format(service: String) {",
        "    service: self.service",
        f"    template: \"{{{{service}}}}/v1/nodes/{c.node_id}\"",
        "  }",
        "  request = JsonObject {",
    ]
    for f in c.inputs:
        lines.append(f"    {f.name}{'' if f.required else '?'}: self.{f.name}")
    lines += [
        "  }",
        "  call = HttpRequest {",
        "    url: url.text",
        "    method: \"POST\"",
        "    body: request.object",
        "  }",
        f"  checked = Cast -> (value: {envelope}) {{ value: call.body }}",
        "  self.passed = checked.value.passed",
        "  self.blocking = checked.value.blockingIssues",
        "  self.evidence = checked.value.evidence",
    ]
    for f in c.outputs:
        lines.append(f"  self.{f.name} = checked.value.outputs.{f.name}")
    lines.append("}")
    return "\n".join(lines) + "\n"


def render_all() -> Dict[str, str]:
    return {c.weft_file: render(c) for c in C.CONTRACTS}


def write_all(nodes_dir: str = NODES_DIR) -> List[str]:
    os.makedirs(nodes_dir, exist_ok=True)
    files = render_all()
    for name, text in files.items():
        with open(os.path.join(nodes_dir, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    for name in os.listdir(nodes_dir):
        if name.endswith(".weft") and name not in files:
            os.remove(os.path.join(nodes_dir, name))
    return sorted(files)


def drift(nodes_dir: str = NODES_DIR) -> List[str]:
    """Names of node files that differ from what the contracts generate."""
    out = []
    files = render_all()
    for name, text in files.items():
        path = os.path.join(nodes_dir, name)
        if not os.path.exists(path):
            out.append(f"missing {name}")
            continue
        with open(path, encoding="utf-8") as f:
            if f.read() != text:
                out.append(f"stale {name}")
    if os.path.isdir(nodes_dir):
        for name in os.listdir(nodes_dir):
            if name.endswith(".weft") and name not in files:
                out.append(f"orphan {name}")
    return out
