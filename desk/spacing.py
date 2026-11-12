"""Electrical spacing model: clearance, creepage, functional spacing and the fabricator minimum kept apart.

Why this exists (UPS_1000, live-test/ups-1000/ROUTING_BLOCKERS.md): `ipc.required_spacing_mil` merges the IPC-2221B
clearance and the IEC 60664-1 creepage with `max()` and the router applied the result (1.25-1.30 mm for 58-70 V nets)
as the copper-to-copper clearance of every object on those nets, including the pads of 1.27 mm-pitch packages whose
copper gap is about 0.65 mm. Creepage is a requirement across an insulation barrier between circuits that must stay
insulated from each other; it is not a trace-to-trace routing rule inside one functional circuit.

This module computes the separate quantities and says which one applies where:

    functional_clearance_mm   IPC-2221B Table 6-1 for the profile's condition (B1..B4, A5..A7): trace-to-trace spacing
    creepage_mm               IEC 60664-1 Table F.4 for the pollution degree / material group: applies only across a
                              declared insulation barrier (reinforced/basic/functional insulation between two groups)
    fabricator_min_mm         the fab's minimum copper-to-copper spacing: the floor everywhere
    pin_field_mm              the smallest neighbour gap at the pads of the parts a net terminates on: what the rule can
                              physically be at those pads; a rule above it cannot be met before any trace exists

`SpacingPolicy` decides what the router rule becomes:

    CREEPAGE_AS_CLEARANCE   the previous behaviour (max of everything). Default: nothing is weakened silently.
    FUNCTIONAL              the IPC clearance as the net rule; creepage enforced only across declared barriers.

A profile may switch to FUNCTIONAL only through `spacing_policy` in design_profile.json, which is a Captain decision
recorded in the ledger (AGENTS.md section A: clearance rule changes need sign-off). Whatever the policy, a rule that
exceeds the pin-field gap of its own pads is reported as an `EngineeringDecision` (BLOCKING) instead of being lowered.

Zero external dependencies.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Sequence

from desk import ipc

MIL = ipc.MIL_PER_MM


class SpacingPolicy(str, enum.Enum):
    CREEPAGE_AS_CLEARANCE = "CREEPAGE_AS_CLEARANCE"
    FUNCTIONAL = "FUNCTIONAL"


@dataclass(frozen=True)
class InsulationBarrier:
    """A declared barrier between two groups of nets (e.g. mains side vs SELV side)."""
    name: str
    nets_a: Sequence[str]
    nets_b: Sequence[str]
    working_voltage_v: float
    insulation: str = "basic"          # functional | basic | reinforced
    pollution_degree: int = 2
    material_group: str = "III"

    def separates(self, net1: str, net2: str) -> bool:
        a, b = set(self.nets_a), set(self.nets_b)
        return (net1 in a and net2 in b) or (net1 in b and net2 in a)


@dataclass
class SpacingRequirement:
    net1: str
    net2: str
    voltage_v: float
    functional_clearance_mm: float
    creepage_mm: Optional[float]           # None when no barrier separates the nets
    fabricator_min_mm: float
    policy: SpacingPolicy
    barrier: Optional[str] = None
    pin_field_mm: Optional[float] = None   # measured neighbour gap at the net's own pads, when known
    table_verified: bool = ipc.verified_against_standard
    pollution_degree: int = 2
    material_group: str = "III"

    @property
    def router_rule_mm(self) -> float:
        """The copper-to-copper rule the router gets for this pair under the policy."""
        if self.policy == SpacingPolicy.CREEPAGE_AS_CLEARANCE:
            legacy = max(self.functional_clearance_mm, self.fabricator_min_mm)
            legacy_creep = (ipc.creepage_mm(self.voltage_v, self.pollution_degree, self.material_group)
                            if abs(self.voltage_v) >= 10.0 else 0.0)
            return max(legacy, legacy_creep)
        base = max(self.functional_clearance_mm, self.fabricator_min_mm)
        if self.creepage_mm is not None:
            base = max(base, self.creepage_mm)
        return base

    @property
    def router_rule_mil(self) -> float:
        return round(self.router_rule_mm * MIL, 2)

    @property
    def meetable_at_pins(self) -> Optional[bool]:
        if self.pin_field_mm is None:
            return None
        return self.router_rule_mm <= self.pin_field_mm + 1e-6

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["policy"] = self.policy.value
        d["router_rule_mm"] = round(self.router_rule_mm, 4)
        d["router_rule_mil"] = self.router_rule_mil
        d["meetable_at_pins"] = self.meetable_at_pins
        return d


@dataclass
class EngineeringDecision:
    """A spacing conflict a human must settle. BLOCKING until an approval references `decision_id`."""
    decision_id: str
    net: str
    rule_mm: float
    pin_field_mm: float
    pads: List[str]
    rule_source: str
    options: List[str]
    status: str = "BLOCKING"
    note: str = "No spacing value was changed automatically (AGENTS.md A: clearance changes need Captain sign-off)."

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def functional_clearance_mm(voltage_v: float, condition: str = "B2") -> float:
    return ipc.clearance_mm(voltage_v, condition)


def creepage_for_barrier(barrier: InsulationBarrier) -> float:
    base = ipc.creepage_mm(barrier.working_voltage_v, barrier.pollution_degree, barrier.material_group)
    return base * 2.0 if barrier.insulation == "reinforced" else base


def requirement(net1: str, net2: str, v1: float, v2: float, condition: str, fab_min_mm: float,
                policy: SpacingPolicy, barriers: Sequence[InsulationBarrier] = (),
                pin_field_mm: Optional[float] = None, pollution_degree: int = 2,
                material_group: str = "III") -> SpacingRequirement:
    v = abs(float(v1) - float(v2))
    creep: Optional[float] = None
    bname: Optional[str] = None
    for b in barriers:
        if b.separates(net1, net2):
            c = creepage_for_barrier(b)
            if creep is None or c > creep:
                creep, bname = c, b.name
    return SpacingRequirement(net1=net1, net2=net2, voltage_v=v, functional_clearance_mm=functional_clearance_mm(v, condition),
                              creepage_mm=creep, fabricator_min_mm=float(fab_min_mm), policy=policy, barrier=bname,
                              pin_field_mm=pin_field_mm, pollution_degree=pollution_degree, material_group=material_group)


def parse_policy(value: Any) -> SpacingPolicy:
    try:
        return SpacingPolicy(str(value).upper())
    except Exception:
        return SpacingPolicy.CREEPAGE_AS_CLEARANCE


def parse_barriers(raw: Any) -> List[InsulationBarrier]:
    out: List[InsulationBarrier] = []
    for b in raw or []:
        if not isinstance(b, dict) or not b.get("name"):
            continue
        out.append(InsulationBarrier(name=str(b["name"]), nets_a=tuple(b.get("nets_a", [])), nets_b=tuple(b.get("nets_b", [])),
                                     working_voltage_v=float(b.get("working_voltage_v", 0.0)),
                                     insulation=str(b.get("insulation", "basic")),
                                     pollution_degree=int(b.get("pollution_degree", 2)),
                                     material_group=str(b.get("material_group", "III"))))
    return out


def decision_for(net: str, rule_mm: float, pin_field_mm: float, pads: Sequence[str], rule_source: str,
                 decision_id: str = "") -> EngineeringDecision:
    import hashlib
    did = decision_id or "SPC-" + hashlib.sha1(f"{net}|{rule_mm:.4f}|{pin_field_mm:.4f}".encode()).hexdigest()[:8]
    return EngineeringDecision(
        decision_id=did, net=net, rule_mm=round(rule_mm, 4), pin_field_mm=round(pin_field_mm, 4), pads=list(pads),
        rule_source=rule_source,
        options=[
            f"Declare the board functional-insulation only (spacing_policy FUNCTIONAL) so {net} gets the IPC-2221B "
            f"clearance and creepage applies only across declared barriers; record the ledger decision.",
            "Verify the IEC 60664-1 printed-wiring column for this pollution degree / material group and declare the "
            "verified value (ipc.verified_against_standard).",
            f"Apply the rule net-to-net away from the pin field and the fabricator minimum inside it (requires a "
            f"pad-local rule the DSN exporter does not emit yet).",
            "Change the package or placement so the pin-field gap meets the rule.",
        ])
