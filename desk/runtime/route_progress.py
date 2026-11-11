"""Routing-stage status for Mission Control (rework item D, 225-minute programme §14).

Reads the files `tools/route.py` and the orchestrator already write under `projects/<P>/state/route/`:
* progress.json       per-pass engine telemetry (best pass, problem nets by name, elapsed vs budget)
* preflight.json      the fail-closed pre-flight verdict
* dense_analysis.json congestion hotspots, corridors and priority order (compacted here)
* routing_attempt.json the last attempt summary when present

No live ECAD access; the files are the only source, so the dashboard shows real state or "absent".

Zero external dependencies.
"""
from __future__ import annotations
import os
import time
from typing import Any, Dict, Optional

from desk.fsutil import read_json

STAGE_TARGET_MIN = 90  # Stage 3 routing target of the 225-minute programme


def _age_s(path: str) -> Optional[float]:
    try:
        return round(time.time() - os.path.getmtime(path), 1)
    except OSError:
        return None


def load_route_progress(project_dir: str) -> Dict[str, Any]:
    route_dir = os.path.join(project_dir, "state", "route")
    progress = read_json(os.path.join(route_dir, "progress.json"), default=None)
    preflight = read_json(os.path.join(route_dir, "preflight.json"), default=None)
    dense = read_json(os.path.join(route_dir, "dense_analysis.json"), default=None)
    attempt = read_json(os.path.join(route_dir, "routing_attempt.json"), default=None)

    out: Dict[str, Any] = {
        "project": project_dir,
        "stage_target_min": STAGE_TARGET_MIN,
        "engine": None,
        "progress": None,
        "preflight": None,
        "dense": None,
        "last_attempt": None,
        "verdict": "NO_ROUTING_DATA",
    }
    if isinstance(progress, dict):
        elapsed = float(progress.get("elapsed_s") or 0.0)
        budget = float(progress.get("budget_s") or 0.0)
        out["engine"] = progress.get("engine")
        out["progress"] = {
            "phase": progress.get("phase"),
            "elapsed_s": elapsed,
            "budget_s": budget,
            "time_remaining_s": round(max(0.0, budget - elapsed), 1) if budget else None,
            "passes": progress.get("passes"),
            "initial_unrouted": progress.get("initial_unrouted"),
            "last_unrouted": progress.get("last_unrouted"),
            "best_unrouted": progress.get("best_unrouted"),
            "best_pass": progress.get("best_pass"),
            "passes_since_best": progress.get("passes_since_best"),
            "restores": progress.get("restores"),
            "problem_nets": progress.get("problem_nets", [])[:12],
            "history": progress.get("history", [])[-20:],
            "updated_age_s": _age_s(os.path.join(route_dir, "progress.json")),
        }
        phase = str(progress.get("phase") or "")
        if phase == "routing":
            out["verdict"] = "ROUTING"
        elif phase == "finished":
            out["verdict"] = "SES_WRITTEN" if (progress.get("last_unrouted") or 0) > 0 else "COMPLETE"
        elif phase in ("timeout", "stopped"):
            out["verdict"] = "STOPPED_NO_SES"
        else:
            out["verdict"] = phase.upper() or "UNKNOWN"
    if isinstance(preflight, dict):
        out["preflight"] = {
            "passed": preflight.get("passed"),
            "errors": preflight.get("errors", []),
            "warnings": preflight.get("warnings", []),
            "planes": f"{preflight.get('planes_in_dsn')}/{preflight.get('planes_declared')}",
            "outline_primitives": preflight.get("outline_primitives"),
            "pads_in_router_keepouts": len(preflight.get("pads_in_router_keepouts", []) or []),
            "updated_age_s": _age_s(os.path.join(route_dir, "preflight.json")),
        }
        if preflight.get("passed") is False and out["verdict"] == "NO_ROUTING_DATA":
            out["verdict"] = "PREFLIGHT_REFUSED"
    if isinstance(dense, dict):
        hs = dense.get("hotspots", []) or []
        out["dense"] = {
            "overall_congestion": dense.get("overall_congestion"),
            "overloaded_cells": dense.get("overloaded_cells"),
            "hotspot_regions": len(hs),
            "ratsnest_crossings": dense.get("ratsnest_crossings"),
            "escape_summary": dense.get("escape_summary"),
            "hotspots": [{"id": h.get("region_id"), "bbox_mm": h.get("bbox_mm"), "score": h.get("max_score"),
                          "causes": h.get("causes"), "strategy": h.get("recommended_strategy")} for h in hs[:8]],
            "corridors": [{"id": c.get("corridor_id"), "bbox_mm": c.get("bbox_mm"), "orientation": c.get("orientation")}
                          for c in (dense.get("corridors", []) or [])[:6]],
            "priority_nets": (dense.get("priority_net_order", []) or [])[:15],
            "plane_nets": dense.get("plane_nets", []),
            "updated_age_s": _age_s(os.path.join(route_dir, "dense_analysis.json")),
        }
    if isinstance(attempt, dict):
        out["last_attempt"] = {k: attempt.get(k) for k in ("attempt_id", "status", "timestamp", "duration_sec", "final_unrouted",
                                                           "connectivity_pct", "mode") if k in attempt}
    return out
