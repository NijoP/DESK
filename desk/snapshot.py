"""Indexed PCB Snapshot and Revision-Aware Cache Engine for DESK.
Builds high-performance spatial and topological indices once per PCB revision
and reuses them across placement, routing, and validation.
Zero external dependencies.
"""
import hashlib
import json
import os
import time
from typing import Dict, List, Tuple, Optional, Any, Set
from desk.models import NetEndpoint, FootprintInvariant
from desk.profiler import TelemetryCollector

MIL = 39.37007874

class IndexedPCBSnapshot:
    """Read-optimized, indexed representation of a PCB document state."""

    def __init__(self, raw_dump: Dict[str, Any], project_id: str = "", revision: str = ""):
        self.raw_dump = raw_dump
        self.project_id = project_id
        self.revision = revision
        self.created_at = time.time()
        self.fingerprint = self._compute_fingerprint(raw_dump)

        # Indices
        self.ref_to_comp: Dict[str, Dict[str, Any]] = {}
        self.id_to_comp: Dict[str, Dict[str, Any]] = {}
        self.comp_to_pads: Dict[str, List[Dict[str, Any]]] = {}
        self.pad_lookup: Dict[Tuple[str, str], Dict[str, Any]] = {}  # (ref, pad_num) -> pad
        self.net_to_endpoints: Dict[str, List[NetEndpoint]] = {}
        self.net_to_components: Dict[str, Set[str]] = {}
        self.layer_to_components: Dict[int, List[str]] = {1: [], 2: [], 11: [], 12: []}
        self.footprint_invariants: Dict[str, FootprintInvariant] = {}
        self.component_requirements: Dict[str, Any] = {}
        self.connectivity_graph: Optional[Any] = None

        self._build_indices()

    @staticmethod
    def _compute_fingerprint(dump: Dict[str, Any]) -> str:
        """Computes a fast, deterministic geometric and netlist SHA-1 fingerprint."""
        h = hashlib.sha1()
        for ref in sorted(dump.keys()):
            c = dump[ref]
            if not isinstance(c, dict): continue
            h.update(ref.encode("utf-8"))
            h.update(str(round(c.get("x", 0.0), 1)).encode("utf-8"))
            h.update(str(round(c.get("y", 0.0), 1)).encode("utf-8"))
            h.update(str(c.get("rot", 0)).encode("utf-8"))
            h.update(str(c.get("layer", 1)).encode("utf-8"))
            for p in c.get("pads", []):
                h.update(str(p.get("num", "")).encode("utf-8"))
                h.update(str(p.get("net", "")).encode("utf-8"))
        return h.hexdigest()[:16]

    def _build_indices(self):
        from desk.component_intel import FootprintIntegrityEngine

        for ref, comp in self.raw_dump.items():
            if not ref or not isinstance(comp, dict): continue
            self.ref_to_comp[ref] = comp
            p_id = comp.get("id")
            if p_id:
                self.id_to_comp[str(p_id)] = comp

            pads = comp.get("pads", [])
            self.comp_to_pads[ref] = pads

            layer = comp.get("layer", 1)
            if layer not in self.layer_to_components:
                self.layer_to_components[layer] = []
            self.layer_to_components[layer].append(ref)

            cx = comp.get("x", 0.0)
            cy = comp.get("y", 0.0)
            rot_deg = comp.get("rot", 0.0) or 0.0
            import math
            rot_rad = math.radians(rot_deg)
            cos_a = math.cos(rot_rad)
            sin_a = math.sin(rot_rad)

            for p in pads:
                num = str(p.get("num", ""))
                net = p.get("net") or ""
                self.pad_lookup[(ref, num)] = p

                if net:
                    if net not in self.net_to_endpoints:
                        self.net_to_endpoints[net] = []
                        self.net_to_components[net] = set()
                    self.net_to_components[net].add(ref)

                    dx = p.get("dx", 0.0)
                    dy = p.get("dy", 0.0)
                    px = cx + dx * cos_a - dy * sin_a
                    py = cy + dx * sin_a + dy * cos_a
                    is_smd = p.get("layer") not in (11, 12)

                    self.net_to_endpoints[net].append(NetEndpoint(
                        ref=ref,
                        pad_num=num,
                        net=net,
                        x_mil=px,
                        y_mil=py,
                        layer=layer if is_smd else 11,
                        is_smd=is_smd
                    ))

            # Footprint invariant
            self.footprint_invariants[ref] = FootprintIntegrityEngine.extract_invariant(ref, comp)

    def get_endpoints_for_net(self, net: str) -> List[NetEndpoint]:
        return self.net_to_endpoints.get(net, [])

    def get_components_for_net(self, net: str) -> Set[str]:
        return self.net_to_components.get(net, set())

    def update_component_placement(self, ref: str, x_mil: float, y_mil: float, rot_deg: float, layer: int):
        """Incrementally updates a single component's coordinates and affected net endpoints."""
        if ref not in self.ref_to_comp: return
        comp = self.ref_to_comp[ref]
        comp["x"] = x_mil
        comp["y"] = y_mil
        comp["rot"] = rot_deg
        comp["layer"] = layer

        import math
        rot_rad = math.radians(rot_deg)
        cos_a = math.cos(rot_rad)
        sin_a = math.sin(rot_rad)

        for p in comp.get("pads", []):
            num = str(p.get("num", ""))
            net = p.get("net")
            if not net or net not in self.net_to_endpoints: continue
            dx = p.get("dx", 0.0)
            dy = p.get("dy", 0.0)
            px = x_mil + dx * cos_a - dy * sin_a
            py = y_mil + dx * sin_a + dy * cos_a
            # Update matching endpoint in-place
            for ep in self.net_to_endpoints[net]:
                if ep.ref == ref and ep.pad_num == num:
                    ep.x_mil = px
                    ep.y_mil = py
                    ep.layer = layer if ep.is_smd else 11
                    break
        
        # Invalidate dependent graph
        self.connectivity_graph = None

class PCBSnapshotCache:
    """Manages in-memory and persistent snapshots, with automatic fingerprint invalidation."""
    _memory_cache: Dict[str, IndexedPCBSnapshot] = {}

    @classmethod
    def get_snapshot(cls, project_dir: str, raw_dump: Optional[Dict[str, Any]] = None) -> IndexedPCBSnapshot:
        collector = TelemetryCollector.get_instance()
        project_dir_abs = os.path.abspath(project_dir)

        if raw_dump is None:
            dump_path = os.path.join(project_dir_abs, "state", "pcb_dump.json")
            if not os.path.exists(dump_path):
                raise FileNotFoundError(f"PCB dump not found at {dump_path}")
            with open(dump_path, encoding="utf-8") as f:
                raw_dump = json.load(f)

        fp = IndexedPCBSnapshot._compute_fingerprint(raw_dump)

        # Check in-memory cache
        if project_dir_abs in cls._memory_cache:
            cached = cls._memory_cache[project_dir_abs]
            if cached.fingerprint == fp:
                collector.record_cache_hit()
                return cached
            else:
                collector.record_cache_miss()

        # Build fresh indexed snapshot
        collector.record_cache_miss()
        snap = IndexedPCBSnapshot(raw_dump, project_id=os.path.basename(project_dir_abs))
        cls._memory_cache[project_dir_abs] = snap
        return snap

    @classmethod
    def invalidate(cls, project_dir: Optional[str] = None):
        if project_dir:
            project_dir_abs = os.path.abspath(project_dir)
            cls._memory_cache.pop(project_dir_abs, None)
        else:
            cls._memory_cache.clear()
