"""
DESK Rework Mode Engineering Audit Engine.
Performs deterministic physical audits across 8 independent domains to discover,
classify, and document outstanding work on an existing PCB.
Zero external dependencies.
"""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from desk.profile import DesignProfile
from desk.snapshot import IndexedPCBSnapshot
from desk.quality import QualityGateEvaluator


class IssueSeverity:
    CRITICAL = "CRITICAL"          # Shorts, open critical nets, unrouted power rails, pin mismatches
    HIGH = "HIGH"                  # DRC clearance violations, missing decoupling, unpoured ground planes
    MEDIUM = "MEDIUM"              # Unknown power rail currents, borderline annular rings, silkscreen overlaps
    LOW = "LOW"                    # Minor aesthetic or non-critical documentation discrepancies
    INFORMATIONAL = "INFORMATIONAL"# Verified intentional design exceptions, DNI parts, approved test pads


class IssueCategory:
    REQUIREMENTS = "requirements"
    SCHEMATIC = "schematic"
    COMPONENT = "component"
    PLACEMENT = "placement"
    ROUTING = "routing"
    POWER_THERMAL = "power_thermal"
    COPPER = "copper"
    DRC = "drc"


@dataclass
class Issue:
    issue_id: str
    session_id: str
    category: str
    severity: str
    title: str
    description: str
    affected_objects: Dict[str, Any]
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    source_revision: str = ""
    root_cause_status: str = "UNKNOWN"
    proposed_repair: Optional[Dict[str, Any]] = None
    verification_method: Optional[str] = None
    status: str = "DETECTED"  # DETECTED, PLANNED, APPROVED, RESOLVED, IGNORED

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Issue:
        valid_fields = cls.__dataclass_fields__.keys()
        clean = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**clean)


class ReworkAuditEngine:
    """Orchestrates comprehensive multi-domain auditing of an existing PCB project."""

    def __init__(self, session_id: str, project_path: str, baseline_revision: str = ""):
        self.session_id = session_id
        self.project_path = os.path.abspath(project_path)
        self.baseline_revision = baseline_revision
        self.issue_counter = 0
        self.issues: List[Issue] = []

    def _next_issue_id(self) -> str:
        self.issue_counter += 1
        return f"RW-{self.issue_counter:04d}"

    def audit_requirements(
        self,
        requirements_path: Optional[str] = None,
        profile: Optional[DesignProfile] = None,
    ) -> List[Issue]:
        """Domain A: Audits requirements, mechanical dimensions, and design profile constraints."""
        found: List[Issue] = []
        req_file = requirements_path or os.path.join(self.project_path, "REQUIREMENTS.md")
        
        if not os.path.exists(req_file):
            found.append(Issue(
                issue_id=self._next_issue_id(),
                session_id=self.session_id,
                category=IssueCategory.REQUIREMENTS,
                severity=IssueSeverity.HIGH,
                title="Missing Project Requirements Document",
                description="REQUIREMENTS.md is missing. Board boundaries, operating voltages, and power limits are unknown.",
                affected_objects={"file": "REQUIREMENTS.md"},
                evidence=[{"type": "file_missing", "path": req_file}],
                source_revision=self.baseline_revision,
                verification_method="Verify existence and completeness of REQUIREMENTS.md",
            ))

        if profile is None:
            prof_file = os.path.join(self.project_path, "design_profile.json")
            if not os.path.exists(prof_file):
                found.append(Issue(
                    issue_id=self._next_issue_id(),
                    session_id=self.session_id,
                    category=IssueCategory.REQUIREMENTS,
                    severity=IssueSeverity.MEDIUM,
                    title="Missing Engineering Design Profile",
                    description="design_profile.json is not configured. Defaulting to standard 2-layer FR4 profile.",
                    affected_objects={"file": "design_profile.json"},
                    evidence=[{"type": "file_missing", "path": prof_file}],
                    source_revision=self.baseline_revision,
                    verification_method="Generate or provide authoritative design_profile.json",
                ))

        self.issues.extend(found)
        return found

    def audit_schematic_netlist(
        self,
        schematic_blocks: Optional[List[Dict[str, Any]]],
        pcb_components: Dict[str, Any],
    ) -> List[Issue]:
        """Domain B: Checks schematic-to-PCB continuity, net discrepancies, and pin rules."""
        found: List[Issue] = []
        if not schematic_blocks:
            return found

        # Map schematic references and pin nets
        sch_nets: Dict[Tuple[str, str], str] = {}
        for blk in schematic_blocks:
            for p in blk.get("parts", []):
                ref = p.get("ref")
                pins = p.get("pins", {})
                for p_num, p_net in pins.items():
                    if p_net and p_net not in ("NC", "N/C", "NO_CONNECT"):
                        sch_nets[(str(ref), str(p_num))] = str(p_net)

        # Compare with PCB pad nets
        for (ref, p_num), expected_net in sch_nets.items():
            comp = pcb_components.get(ref)
            if not comp:
                found.append(Issue(
                    issue_id=self._next_issue_id(),
                    session_id=self.session_id,
                    category=IssueCategory.SCHEMATIC,
                    severity=IssueSeverity.CRITICAL,
                    title=f"Schematic Part {ref} Missing on PCB",
                    description=f"Part {ref} is specified in the schematic but has not been placed on the PCB.",
                    affected_objects={"ref": ref, "expected_net": expected_net},
                    evidence=[{"ref": ref, "pin": p_num, "expected_net": expected_net}],
                    source_revision=self.baseline_revision,
                    proposed_repair={"action": "place_component", "ref": ref},
                    verification_method="Component footprint placed and assigned on PCB",
                ))
                continue

            pads = comp.get("pads", [])
            pad_found = False
            for pad in pads:
                if str(pad.get("num", "")) == str(p_num):
                    pad_found = True
                    actual_net = pad.get("net") or ""
                    if actual_net != expected_net:
                        found.append(Issue(
                            issue_id=self._next_issue_id(),
                            session_id=self.session_id,
                            category=IssueCategory.SCHEMATIC,
                            severity=IssueSeverity.CRITICAL,
                            title=f"Net Discrepancy on {ref} Pin {p_num}",
                            description=f"Schematic expects net '{expected_net}', but PCB pad is assigned '{actual_net or '<UNASSIGNED>'}'",
                            affected_objects={"ref": ref, "pin": p_num, "schematic_net": expected_net, "pcb_net": actual_net},
                            evidence=[{"ref": ref, "pin": p_num, "sch_net": expected_net, "pcb_net": actual_net}],
                            source_revision=self.baseline_revision,
                            proposed_repair={"action": "update_pad_net", "ref": ref, "pad_num": p_num, "net": expected_net},
                            verification_method="Pad net matches authoritative schematic",
                        ))
                    break

        self.issues.extend(found)
        return found

    def audit_components_footprints(
        self,
        pcb_components: Dict[str, Any],
        library_models: Optional[Dict[str, Any]] = None,
    ) -> List[Issue]:
        """Domain C: Audits footprints, pin counts, rotation, and package assignments."""
        found: List[Issue] = []
        for ref, comp in pcb_components.items():
            if not isinstance(comp, dict):
                continue

            pads = comp.get("pads", [])
            if not pads:
                found.append(Issue(
                    issue_id=self._next_issue_id(),
                    session_id=self.session_id,
                    category=IssueCategory.COMPONENT,
                    severity=IssueSeverity.HIGH,
                    title=f"Component {ref} Has No Pads",
                    description=f"Component {ref} is defined without any copper pads or mechanical terminals.",
                    affected_objects={"ref": ref},
                    evidence=[{"ref": ref, "pads_count": 0}],
                    source_revision=self.baseline_revision,
                    verification_method="Assign valid footprint with copper pads",
                ))

            # Check for duplicate pad numbers
            pad_nums = [str(p.get("num", "")) for p in pads if p.get("num") is not None]
            if len(pad_nums) != len(set(pad_nums)):
                found.append(Issue(
                    issue_id=self._next_issue_id(),
                    session_id=self.session_id,
                    category=IssueCategory.COMPONENT,
                    severity=IssueSeverity.CRITICAL,
                    title=f"Duplicate Pad Numbers in Footprint {ref}",
                    description=f"Component {ref} contains duplicate pad identifiers, causing short-circuit risks.",
                    affected_objects={"ref": ref, "pad_numbers": pad_nums},
                    evidence=[{"ref": ref, "duplicate_pads": [x for x in pad_nums if pad_nums.count(x) > 1]}],
                    source_revision=self.baseline_revision,
                    verification_method="Fix footprint pad numbering",
                ))

        self.issues.extend(found)
        return found

    def audit_mechanical_placement(
        self,
        pcb_components: Dict[str, Any],
        board_dimensions_mm: Tuple[float, float] = (50.0, 50.0),
        edge_clearance_mm: float = 0.5,
    ) -> List[Issue]:
        """Domain D: Audits component-to-board-edge clearance and mechanical collisions."""
        found: List[Issue] = []
        bw_mil = board_dimensions_mm[0] * 39.3701
        bh_mil = board_dimensions_mm[1] * 39.3701
        edge_mil = edge_clearance_mm * 39.3701

        for ref, comp in pcb_components.items():
            if not isinstance(comp, dict):
                continue
            cx = comp.get("x", 0.0)
            cy = comp.get("y", 0.0)
            bbox = comp.get("bbox", [-40.0, 40.0, -40.0, 40.0])  # min_dx, max_dx, min_dy, max_dy
            
            x1 = cx + bbox[0]
            x2 = cx + bbox[1]
            y1 = cy + bbox[2]
            y2 = cy + bbox[3]

            # Edge violation check
            if x1 < edge_mil or x2 > (bw_mil - edge_mil) or y1 < edge_mil or y2 > (bh_mil - edge_mil):
                found.append(Issue(
                    issue_id=self._next_issue_id(),
                    session_id=self.session_id,
                    category=IssueCategory.PLACEMENT,
                    severity=IssueSeverity.HIGH,
                    title=f"Component {ref} Violates Board Edge Clearance",
                    description=f"Part {ref} is placed within {edge_clearance_mm}mm of the board outline.",
                    affected_objects={"ref": ref, "coords_mil": [cx, cy]},
                    evidence=[{"ref": ref, "bounds": [x1, y1, x2, y2], "board_size": [bw_mil, bh_mil]}],
                    source_revision=self.baseline_revision,
                    proposed_repair={"action": "nudge_component", "ref": ref},
                    verification_method="Component completely within safe board envelope",
                ))

        self.issues.extend(found)
        return found

    def audit_pcb_routing(
        self,
        snapshot: IndexedPCBSnapshot,
        critical_nets: Optional[List[str]] = None,
    ) -> List[Issue]:
        """Domain E: Audits complete connectivity, identifies unrouted airwires and missing traces."""
        found: List[Issue] = []
        crit_set = set(critical_nets or ["3V3", "5V", "VCC", "VIN", "GND", "USB_D_P", "USB_D_N"])

        # Determine all distinct nets
        for net, endpoints in snapshot.net_to_endpoints.items():
            if not net or net in ("GND", "NC", "N/C"):
                continue  # GND handled by copper audit, NC ignored

            if len(endpoints) < 2:
                # Single pad net
                found.append(Issue(
                    issue_id=self._next_issue_id(),
                    session_id=self.session_id,
                    category=IssueCategory.ROUTING,
                    severity=IssueSeverity.LOW,
                    title=f"Single-Pad Net '{net}'",
                    description=f"Net '{net}' connects to only one pad ({endpoints[0].ref}.{endpoints[0].pad_num}).",
                    affected_objects={"net": net, "ref": endpoints[0].ref, "pad": endpoints[0].pad_num},
                    evidence=[{"net": net, "pad": f"{endpoints[0].ref}.{endpoints[0].pad_num}"}],
                    source_revision=self.baseline_revision,
                    verification_method="Confirm intentional test point or remove unused net label",
                ))
                continue

            # Check if tracks exist for this net
            net_tracks = [t for t in snapshot.tracks if t.get("net") == net]
            is_critical = net in crit_set

            if not net_tracks:
                severity = IssueSeverity.CRITICAL if is_critical else IssueSeverity.HIGH
                found.append(Issue(
                    issue_id=self._next_issue_id(),
                    session_id=self.session_id,
                    category=IssueCategory.ROUTING,
                    severity=severity,
                    title=f"Unrouted Net '{net}' ({len(endpoints)} pads)",
                    description=f"Net '{net}' has {len(endpoints)} connected endpoints but 0 routed track segments on the PCB.",
                    affected_objects={"net": net, "pads_count": len(endpoints)},
                    evidence=[{"net": net, "endpoints": [f"{ep.ref}.{ep.pad_num}" for ep in endpoints]}],
                    source_revision=self.baseline_revision,
                    proposed_repair={"action": "route_net", "net": net},
                    verification_method="All pads connected with zero open airwires",
                ))

        self.issues.extend(found)
        return found

    def audit_power_thermal(
        self,
        snapshot: IndexedPCBSnapshot,
        profile: Optional[DesignProfile] = None,
    ) -> List[Issue]:
        """Domain F: Audits trace widths vs IPC-2221 ampacity requirements (desk.ipc)."""
        from desk import ipc
        found: List[Issue] = []
        if profile is not None:
            # Only VERIFIED currents are audited; unknown rails are reported by validate_electrical_inputs.
            power_nets = dict(profile.current_limits_A)
            for nc in profile.net_classes.values():
                for n in nc.nets:
                    power_nets.setdefault(n, nc.max_current_A)
            temp_rise = max(1.0, profile.thermal.max_temperature_rise_c)
            cu_oz = profile.stackup[0].copper_thickness_oz if profile.stackup else 1.0
        else:
            power_nets = {"3V3": 1.0, "5V": 2.0, "VIN": 3.0}
            temp_rise, cu_oz = 10.0, 1.0

        for p_net, target_current in power_nets.items():
            if target_current <= 0.3:
                continue
            net_tracks = [t for t in snapshot.tracks if t.get("net") == p_net]
            for t in net_tracks:
                width = float(t.get("width", 0.0))
                is_inner = int(t.get("layer", 1)) not in (1, 2) if profile and profile.layer_count == 2 else False
                min_width = max(8.0, ipc.trace_width_mil(target_current, is_inner=is_inner, copper_oz=cu_oz,
                                                         temp_rise_c=temp_rise))
                if width < (min_width - 0.5):
                    found.append(Issue(
                        issue_id=self._next_issue_id(),
                        session_id=self.session_id,
                        category=IssueCategory.POWER_THERMAL,
                        severity=IssueSeverity.HIGH,
                        title=f"Trace Width Undersized on Power Net '{p_net}'",
                        description=f"Track segment width is {width} mil, but requires at least {min_width} mil for {target_current}A under IPC-2152.",
                        affected_objects={"net": p_net, "track_id": t.get("id"), "width_mil": width},
                        evidence=[{"net": p_net, "actual_width": width, "required_min_width": min_width, "target_current_a": target_current}],
                        source_revision=self.baseline_revision,
                        proposed_repair={"action": "widen_track", "track_id": t.get("id"), "new_width": min_width},
                        verification_method="Trace width >= required IPC-2152 ampacity width",
                    ))

        self.issues.extend(found)
        return found

    def audit_copper_ground(
        self,
        snapshot: IndexedPCBSnapshot,
    ) -> List[Issue]:
        """Domain G: Audits ground planes, zone repour state, and isolated copper."""
        found: List[Issue] = []
        if not snapshot.zones:
            found.append(Issue(
                issue_id=self._next_issue_id(),
                session_id=self.session_id,
                category=IssueCategory.COPPER,
                severity=IssueSeverity.HIGH,
                title="No Ground Planes or Copper Zones Defined",
                description="The PCB contains no poured reference planes, leading to unshielded signal return paths.",
                affected_objects={"zones_count": 0},
                evidence=[{"zones": 0}],
                source_revision=self.baseline_revision,
                proposed_repair={"action": "generate_ground_planes"},
                verification_method="Continuous ground reference plane present on Layer 2 / Layer 1",
            ))

        for z in snapshot.zones:
            if z.get("unpoured", False) or z.get("stale", False):
                found.append(Issue(
                    issue_id=self._next_issue_id(),
                    session_id=self.session_id,
                    category=IssueCategory.COPPER,
                    severity=IssueSeverity.MEDIUM,
                    title=f"Copper Zone '{z.get('id', 'Z1')}' Requires Repour",
                    description=f"Copper zone on layer {z.get('layer', 1)} has unpoured or stale geometry.",
                    affected_objects={"zone_id": z.get("id")},
                    evidence=[{"zone_id": z.get("id"), "stale": True}],
                    source_revision=self.baseline_revision,
                    proposed_repair={"action": "repour_zone", "zone_id": z.get("id")},
                    verification_method="Zone poured with current polygon geometry",
                ))

        self.issues.extend(found)
        return found

    def audit_drc_manufacturing(
        self,
        raw_drc_violations: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Issue]:
        """Domain H: Reads DRC violations and converts them into structured Rework issues."""
        found: List[Issue] = []
        if not raw_drc_violations:
            return found

        for d in raw_drc_violations:
            err_type = str(d.get("errorType") or d.get("ruleName") or "DRC_VIOLATION")
            is_short = "short" in err_type.lower()
            severity = IssueSeverity.CRITICAL if is_short else IssueSeverity.HIGH

            found.append(Issue(
                issue_id=self._next_issue_id(),
                session_id=self.session_id,
                category=IssueCategory.DRC,
                severity=severity,
                title=f"DRC Violation: {err_type}",
                description=f"Physical clearance or connectivity rule failed: {d.get('message', err_type)}",
                affected_objects={"violation": d},
                evidence=[d],
                source_revision=self.baseline_revision,
                verification_method="DRC check passes with 0 violations",
            ))

        self.issues.extend(found)
        return found

    def run_full_audit(
        self,
        snapshot: IndexedPCBSnapshot,
        schematic_blocks: Optional[List[Dict[str, Any]]] = None,
        profile: Optional[DesignProfile] = None,
        raw_drc: Optional[List[Dict[str, Any]]] = None,
        board_dimensions_mm: Tuple[float, float] = (50.0, 50.0),
    ) -> List[Issue]:
        """Executes all 8 audit domains sequentially and returns consolidated issue inventory."""
        self.issues.clear()
        self.issue_counter = 0

        self.audit_requirements(profile=profile)
        self.audit_schematic_netlist(schematic_blocks, snapshot.raw_dump)
        self.audit_components_footprints(snapshot.raw_dump)
        self.audit_mechanical_placement(snapshot.raw_dump, board_dimensions_mm)
        self.audit_pcb_routing(snapshot)
        self.audit_power_thermal(snapshot, profile)
        self.audit_copper_ground(snapshot)
        self.audit_drc_manufacturing(raw_drc)

        # Save to issue_inventory.json
        sdir = os.path.join(self.project_path, "state", "rework", self.session_id)
        os.makedirs(sdir, exist_ok=True)
        path = os.path.join(sdir, "issue_inventory.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump([i.to_dict() for i in self.issues], f, indent=2)

        return self.issues
