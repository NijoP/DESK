"""Intelligence allocation: which kind of task gets which tier of model, as data.

Principles (Captain's directive, "Intelligence allocation" and "DESK is the orchestrator"):
  * deterministic engineering code first: calculations, validation, DRC/ERC and repetitive
    operations are tier 0 and never reach a model;
  * small, cheap models for classification, extraction and straightforward planning (tier 1);
  * stronger reasoning models for power electronics, RF, mains safety, system architecture and
    engineering trade-offs (tier 3), each challenged by an independent verifier;
  * the model proposes; deterministic engines calculate; validators verify; the engineer approves
    design mutations. A model is never the sole authority for electrical correctness.

The policy is plain data (POLICY below). An operator may override any top-level key with a JSON
file named by DESK_MODEL_POLICY_FILE, for example to point tier 1 at a local model:

    {"tiers": {"1": ["ollama:example-small:8b"], "verifier": ["gemini:example-verifier"]}}

Default tier routes are the NVIDIA NIM models DESK verified (capabilities.py) and match the
nvidia column of router._DEFAULT_MODELS (a test keeps them in step), so nothing changes for an
operator who configures nothing.

Zero external dependencies.
"""
from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Iterable, List, Optional, Tuple

from desk import config as deskcfg
from desk.orchestrator.providers.base import ModelRoute

AUTHORITY = ("Models interpret requirements and propose. Deterministic engines perform calculations; validators "
             "independently verify; the engineer approves important design mutations. A model is never the sole "
             "authority for electrical correctness.")

_ULTRA = "nvidia:nvidia/nemotron-3-ultra-550b-a55b"
_SUPER = "nvidia:nvidia/nemotron-3.5-super-vl-120b-a12b"
_LIGHT = "nvidia:nvidia/nemotron-3.5-lightning-30b-a3b"

POLICY: Dict[str, Any] = {
    "version": 1,
    "authority": AUTHORITY,
    "task_classes": {
        # tier 0: deterministic DESK code only
        "calculation":          {"tier": 0, "why": "electrical and geometric arithmetic belongs to DESK's engines"},
        "validation":           {"tier": 0, "why": "gates, lint and verify are deterministic validators"},
        "drc_erc":              {"tier": 0, "why": "design-rule and electrical-rule checks are deterministic"},
        "repetitive":           {"tier": 0, "why": "bulk, repeatable operations run as code"},
        # tier 1: small model
        "classification":       {"tier": 1, "json": True, "why": "short structured answer"},
        "extraction":           {"tier": 1, "json": True, "why": "pull fields from text or datasheet excerpts"},
        "simple_planning":      {"tier": 1, "why": "ordering of known steps"},
        # tier 2: capable model, output gated by a deterministic validator
        "planning":             {"tier": 2, "why": "multi-step plan over DESK tools"},
        "schematic_review":     {"tier": 2, "verify": True, "why": "review findings are challenged"},
        # tier 3: strong reasoning model plus an independent verifier
        "power_electronics":    {"tier": 3, "verify": True, "why": "thermal, switching and safety trade-offs"},
        "rf":                   {"tier": 3, "verify": True, "why": "impedance, layout and coexistence trade-offs"},
        "mains_safety":         {"tier": 3, "verify": True, "why": "creepage, clearance and isolation decisions"},
        "system_architecture":  {"tier": 3, "verify": True, "why": "partitioning and interface decisions"},
        "engineering_tradeoff": {"tier": 3, "verify": True, "why": "competing requirements need challenge"},
        # tier 4: frontier escalation
        "contradiction_resolution": {"tier": 4, "verify": True, "why": "conflicting evidence or a design pivot"},
        # the verifier role itself
        "verification":         {"tier": "verifier", "why": "independent challenge of another model's proposal"},
    },
    # A request tagged with any of these domains is raised to at least tier 3 with a verifier,
    # whatever its task class (a "simple" question about a mains dropper is not simple).
    "escalate_domains": ["power_electronics", "rf", "mains", "high_voltage", "high_current", "battery",
                         "motor_drive", "isolation"],
    "tiers": {
        "1": [_LIGHT],
        "2": [_SUPER, _ULTRA],
        "3": [_ULTRA],
        "4": [_ULTRA],
        "verifier": [_SUPER, _ULTRA],
    },
    # mirror router._DEFAULT_THINKING / _DEFAULT_TIMEOUTS
    "thinking": {"1": "off", "2": "off", "3": "medium", "4": "high", "verifier": "medium"},
    "timeouts_s": {"1": 30.0, "2": 90.0, "3": 180.0, "4": 300.0, "verifier": 180.0},
}


def load_policy(path: Optional[str] = None) -> Dict[str, Any]:
    """Built-in policy with the operator file's top-level keys merged over the built-in ones.
    The authority statement is not configurable."""
    pol = copy.deepcopy(POLICY)
    path = path or (deskcfg.get("DESK_MODEL_POLICY_FILE") or "").strip()
    if path and os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            over = json.load(f)
        if isinstance(over, dict):
            for k, v in over.items():
                if k == "authority":
                    continue
                if isinstance(v, dict) and isinstance(pol.get(k), dict):
                    pol[k].update(v)
                else:
                    pol[k] = v
    return pol


@dataclass
class Allocation:
    task_class: str
    tier: Any                                   # 0..4 or "verifier"
    deterministic: bool
    routes: List[str] = field(default_factory=list)
    thinking: Optional[str] = None
    timeout_s: Optional[float] = None
    json: bool = False
    verify: bool = False
    verifier_routes: List[str] = field(default_factory=list)
    verifier_independence: str = "none"         # provider | model | none
    escalated_by: List[str] = field(default_factory=list)
    why: str = ""
    authority: str = AUTHORITY
    open_issue: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def model_routes(self, registry) -> List[ModelRoute]:
        return [registry.parse_route(r) for r in self.routes]

    def verifier_model_routes(self, registry) -> List[ModelRoute]:
        return [registry.parse_route(r) for r in self.verifier_routes]


def _provider_of(route: str) -> str:
    return route.partition(":")[0]


def independent_verifiers(primary: Optional[str], candidates: Iterable[str]) -> Tuple[List[str], str]:
    """Order verifier candidates: a different provider first, then a different model on the same
    provider. The primary route is never its own verifier. Returns (routes, independence)."""
    cands = [c for c in dict.fromkeys(candidates) if c != primary]
    if not primary:
        return cands, ("provider" if cands else "none")
    p = _provider_of(primary)
    other_provider = [c for c in cands if _provider_of(c) != p]
    same_provider = [c for c in cands if _provider_of(c) == p]
    level = "provider" if other_provider else "model" if same_provider else "none"
    return other_provider + same_provider, level


def allocate(task_class: str, domains: Iterable[str] = (), policy: Optional[Dict[str, Any]] = None) -> Allocation:
    """Map a task class (plus optional domain tags) to a tier, model routes and verifier routes.
    An unknown task class is refused: the caller must classify the work, not guess."""
    pol = policy if policy is not None else load_policy()
    classes = pol.get("task_classes") or {}
    if task_class not in classes:
        raise ValueError(f"unknown task class '{task_class}'; known: {', '.join(sorted(classes))}")
    spec = classes[task_class]
    tier = spec.get("tier", 2)
    verify = bool(spec.get("verify", False))
    escalated = [d for d in domains if d in set(pol.get("escalate_domains") or [])]
    if tier == 0:
        return Allocation(task_class=task_class, tier=0, deterministic=True, why=spec.get("why", ""),
                          escalated_by=escalated)
    if escalated and tier != "verifier" and int(tier) < 3:
        tier, verify = 3, True
    key = str(tier)
    tiers = pol.get("tiers") or {}
    routes = list(tiers.get(key) or [])
    alloc = Allocation(task_class=task_class, tier=tier, deterministic=False, routes=routes,
                       thinking=(pol.get("thinking") or {}).get(key), timeout_s=(pol.get("timeouts_s") or {}).get(key),
                       json=bool(spec.get("json", False)), verify=verify, escalated_by=escalated, why=spec.get("why", ""))
    if not routes:
        alloc.open_issue = f"no model routes configured for tier {key}"
    if verify:
        pool = list(tiers.get("verifier") or []) + routes
        alloc.verifier_routes, alloc.verifier_independence = independent_verifiers(routes[0] if routes else None, pool)
        if not alloc.verifier_routes:
            alloc.open_issue = ("no independent verifier model is configured; the decision goes to the engineer "
                                "with the proposal marked unverified")
    return alloc
