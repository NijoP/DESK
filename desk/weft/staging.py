"""Assemble a runnable Weft project for one DESK workflow.

A workflow in the repo is only its own files (weft.toml, src/). Staging copies it into a build folder and adds
the DESK node library under nodes/. The Weft standard library (nodes/base_catalog/) comes from the pinned Weft
checkout: `weft catalog update` puts it there on a machine with a Weft install; the compiler harness reads it
straight from the checkout instead.

The staged folder is build output (.desk_weft/ is ignored by git). A Weft install refuses a project on a Windows
drive mounted in WSL, so for a WSL runtime the staged folder is copied into the Linux home (desk.weft.runtime).
"""
from __future__ import annotations

import json
import os
import shutil
from typing import Any, Dict, List

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WEFT_DIR = os.path.join(REPO, "integrations", "weft")
WORKFLOWS_DIR = os.path.join(WEFT_DIR, "workflows")
NODES_SRC = os.path.join(WEFT_DIR, "nodes")
PIN_FILE = os.path.join(WEFT_DIR, "WEFT_PIN.json")
BUILD_DIR = os.path.join(REPO, ".desk_weft")
NODE_PACKAGES = ("desk", "desk_stages")
KEPT_ACROSS_RESTAGE = ("nodes/base_catalog", ".weft")


def pin() -> Dict[str, Any]:
    with open(PIN_FILE, encoding="utf-8") as f:
        return json.load(f)


def workflows() -> List[Dict[str, str]]:
    out = []
    if os.path.isdir(WORKFLOWS_DIR):
        for name in sorted(os.listdir(WORKFLOWS_DIR)):
            d = os.path.join(WORKFLOWS_DIR, name)
            entry = os.path.join(d, "src", "main.weft")
            if os.path.isfile(os.path.join(d, "weft.toml")) and os.path.isfile(entry):
                with open(entry, encoding="utf-8") as f:
                    first = f.readline().lstrip("# ").strip()
                out.append({"name": name, "path": d, "summary": first})
    return out


def workflow_dir(name: str) -> str:
    for w in workflows():
        if w["name"] == name:
            return w["path"]
    raise KeyError(f"no workflow '{name}' (have: {', '.join(w['name'] for w in workflows()) or 'none'})")


def stage(name: str, build_dir: str = BUILD_DIR) -> str:
    """Copy the workflow and the DESK node library into <build_dir>/stage/<name>. Returns that folder."""
    src = workflow_dir(name)
    dst = os.path.join(build_dir, "stage", name)
    # What Weft fetched or built for this folder survives a restage: the standard library mirror (`weft catalog
    # update`) and the project's .weft/ build cache (weft-compiler Project::state_dir). Neither is DESK source.
    kept = []
    for rel in KEPT_ACROSS_RESTAGE:
        here = os.path.join(dst, *rel.split("/"))
        if os.path.isdir(here):
            tmp = f"{dst}.keep.{rel.replace('/', '_')}"
            shutil.rmtree(tmp, ignore_errors=True)
            shutil.move(here, tmp)
            kept.append((tmp, here))
    shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(src, dst)
    for pkg in NODE_PACKAGES:
        shutil.copytree(os.path.join(NODES_SRC, pkg), os.path.join(dst, "nodes", pkg))
    for tmp, here in kept:
        os.makedirs(os.path.dirname(here), exist_ok=True)
        shutil.move(tmp, here)
    with open(os.path.join(dst, "DESK_STAGED.json"), "w", encoding="utf-8") as f:
        json.dump({"workflow": name, "weft_pin": pin()["commit"]}, f)
    return dst
