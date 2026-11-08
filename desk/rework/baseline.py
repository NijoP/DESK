"""
DESK Rework Baseline Capture, Multi-Domain Revision Fingerprinting & Change Detection.
Captures the immutable starting state of an existing PCB project and detects external
modifications made outside DESK.
Zero external dependencies.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from desk.snapshot import IndexedPCBSnapshot


@dataclass
class BaselineSnapshot:
    """Immutable baseline representation of an existing project prior to rework."""
    session_id: str
    project_id: str
    project_path: str
    captured_at: float
    
    # Domain Revision Hashes
    geometry_rev: str
    connectivity_rev: str
    stackup_rev: str
    copper_rev: str
    rules_rev: str
    schematic_rev: str
    composite_fingerprint: str
    
    # Raw Physical Primitives
    components_count: int = 0
    tracks_count: int = 0
    vias_count: int = 0
    zones_count: int = 0
    nets_count: int = 0
    
    # Serialized Data
    components: Dict[str, Any] = field(default_factory=dict)
    tracks: List[Dict[str, Any]] = field(default_factory=list)
    vias: List[Dict[str, Any]] = field(default_factory=list)
    zones: List[Dict[str, Any]] = field(default_factory=list)
    schematic: Dict[str, Any] = field(default_factory=dict)
    stackup: Optional[Any] = None
    rules: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BaselineSnapshot:
        valid_fields = cls.__dataclass_fields__.keys()
        clean = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**clean)


class BaselineCaptureEngine:
    """Captures and persists immutable baseline snapshots."""

    @staticmethod
    def _compute_schematic_rev(schematic_data: Dict[str, Any]) -> str:
        """Computes a SHA-1 fingerprint for schematic blocks and net connections."""
        if not schematic_data:
            return "sch_none"
        raw = json.dumps(schematic_data, sort_keys=True, default=str)
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]

    @classmethod
    def capture_from_data(
        cls,
        session_id: str,
        project_path: str,
        components_dump: Dict[str, Any],
        tracks: Optional[List[Dict[str, Any]]] = None,
        vias: Optional[List[Dict[str, Any]]] = None,
        zones: Optional[List[Dict[str, Any]]] = None,
        schematic_data: Optional[Dict[str, Any]] = None,
        stackup: Optional[Any] = None,
        rules: Optional[Dict[str, Any]] = None,
    ) -> BaselineSnapshot:
        """Builds an IndexedPCBSnapshot, computes all domain fingerprints, and creates BaselineSnapshot."""
        norm_path = os.path.abspath(project_path)
        proj_id = os.path.basename(norm_path)

        indexed = IndexedPCBSnapshot(
            raw_dump=components_dump,
            project_id=proj_id,
            tracks=tracks or [],
            vias=vias or [],
            zones=zones or [],
            stackup=stackup,
            rules=rules or {},
        )

        sch_rev = cls._compute_schematic_rev(schematic_data or {})
        
        # Composite includes schematic revision as well
        h_comp = hashlib.sha1(f"{indexed.fingerprint}:{sch_rev}".encode("utf-8"))
        final_fingerprint = h_comp.hexdigest()[:16]

        unique_nets: Set[str] = set()
        for c in components_dump.values():
            if isinstance(c, dict):
                for p in c.get("pads", []):
                    net = p.get("net")
                    if net:
                        unique_nets.add(net)

        baseline = BaselineSnapshot(
            session_id=session_id,
            project_id=proj_id,
            project_path=norm_path,
            captured_at=time.time(),
            geometry_rev=indexed.geometry_rev,
            connectivity_rev=indexed.connectivity_rev,
            stackup_rev=indexed.stackup_rev,
            copper_rev=indexed.copper_rev,
            rules_rev=indexed.rules_rev,
            schematic_rev=sch_rev,
            composite_fingerprint=final_fingerprint,
            components_count=len(components_dump),
            tracks_count=len(tracks or []),
            vias_count=len(vias or []),
            zones_count=len(zones or []),
            nets_count=len(unique_nets),
            components=components_dump,
            tracks=tracks or [],
            vias=vias or [],
            zones=zones or [],
            schematic=schematic_data or {},
            stackup=stackup,
            rules=rules or {},
        )
        return baseline

    @classmethod
    def save_baseline(cls, baseline: BaselineSnapshot) -> str:
        """Persists the baseline to projects/<P>/state/rework/<SESSION_ID>/baseline.json atomically."""
        sdir = os.path.join(baseline.project_path, "state", "rework", baseline.session_id)
        os.makedirs(sdir, exist_ok=True)
        path = os.path.join(sdir, "baseline.json")
        tmp_path = path + f".tmp_{hashlib.sha1(str(time.time()).encode()).hexdigest()[:6]}"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(baseline.to_dict(), f, indent=2)
        os.replace(tmp_path, path)
        return path

    @classmethod
    def load_baseline(cls, project_path: str, session_id: str) -> Optional[BaselineSnapshot]:
        """Loads baseline snapshot from disk."""
        path = os.path.join(project_path, "state", "rework", session_id, "baseline.json")
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return BaselineSnapshot.from_dict(data)
        except Exception:
            return None

    @classmethod
    def detect_external_modifications(
        cls,
        baseline: BaselineSnapshot,
        current_components: Dict[str, Any],
        current_tracks: Optional[List[Dict[str, Any]]] = None,
        current_vias: Optional[List[Dict[str, Any]]] = None,
        current_zones: Optional[List[Dict[str, Any]]] = None,
        current_stackup: Optional[Any] = None,
        current_rules: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, List[str], Dict[str, Any]]:
        """
        Compares current state against baseline snapshot.
        Returns (has_modified, changed_domains, diff_summary).
        """
        curr = IndexedPCBSnapshot(
            raw_dump=current_components,
            project_id=baseline.project_id,
            tracks=current_tracks or [],
            vias=current_vias or [],
            zones=current_zones or [],
            stackup=current_stackup,
            rules=current_rules or {},
        )

        changed_domains = []
        if curr.geometry_rev != baseline.geometry_rev:
            changed_domains.append("geometry")
        if curr.connectivity_rev != baseline.connectivity_rev:
            changed_domains.append("connectivity")
        if curr.stackup_rev != baseline.stackup_rev:
            changed_domains.append("stackup")
        if curr.copper_rev != baseline.copper_rev:
            changed_domains.append("copper")
        if curr.rules_rev != baseline.rules_rev:
            changed_domains.append("rules")

        has_modified = len(changed_domains) > 0
        diff_summary = {
            "has_modified": has_modified,
            "changed_domains": changed_domains,
            "baseline_fingerprint": baseline.composite_fingerprint,
            "current_fingerprint": curr.fingerprint,
            "components_delta": len(current_components) - baseline.components_count,
            "tracks_delta": len(current_tracks or []) - baseline.tracks_count,
            "vias_delta": len(current_vias or []) - baseline.vias_count,
        }
        return has_modified, changed_domains, diff_summary
