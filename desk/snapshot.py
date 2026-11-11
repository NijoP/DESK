"""Indexed PCB Snapshot and Revision-Aware Cache Engine for DESK.
Builds high-performance spatial and topological indices once per PCB revision
and reuses them across placement, routing, and validation.
Features:
- Complete multi-domain fingerprinting (components, tracks, vias, zones, stackup, rules)
- 2D Spatial Grid Partitioning for fast clearance queries
- Domain-specific revision tracking (geometry, connectivity, stackup, copper, rules)
- Incremental update engine ensuring:
  RESULT_FROM_INCREMENTAL_UPDATE == RESULT_FROM_FULL_REBUILD
Zero external dependencies.
"""
import hashlib
import json
import os
import time
import math
from typing import Dict, List, Tuple, Optional, Any, Set
from desk.models import NetEndpoint, FootprintInvariant
from desk.profiler import TelemetryCollector

MIL = 39.37007874

class SpatialGridIndex:
    """2D Spatial hash grid for accelerated bounding box and proximity queries."""

    def __init__(self, cell_size_mil: float = 100.0):
        self.cell_size = cell_size_mil
        self.cells: Dict[Tuple[int, int], Set[str]] = {}
        self.item_boxes: Dict[str, Tuple[float, float, float, float]] = {}

    def _get_cells(self, x1: float, y1: float, x2: float, y2: float) -> List[Tuple[int, int]]:
        gx1 = int(math.floor(min(x1, x2) / self.cell_size))
        gy1 = int(math.floor(min(y1, y2) / self.cell_size))
        gx2 = int(math.floor(max(x1, x2) / self.cell_size))
        gy2 = int(math.floor(max(y1, y2) / self.cell_size))
        cells = []
        for gx in range(gx1, gx2 + 1):
            for gy in range(gy1, gy2 + 1):
                cells.append((gx, gy))
        return cells

    def insert(self, item_id: str, x1: float, y1: float, x2: float, y2: float):
        self.remove(item_id)
        self.item_boxes[item_id] = (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
        for cell in self._get_cells(x1, y1, x2, y2):
            if cell not in self.cells:
                self.cells[cell] = set()
            self.cells[cell].add(item_id)

    def remove(self, item_id: str):
        if item_id in self.item_boxes:
            box = self.item_boxes.pop(item_id)
            for cell in self._get_cells(*box):
                if cell in self.cells:
                    self.cells[cell].discard(item_id)
                    if not self.cells[cell]:
                        del self.cells[cell]

    def query_rect(self, x1: float, y1: float, x2: float, y2: float) -> Set[str]:
        qx1, qy1, qx2, qy2 = min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)
        candidates = set()
        for cell in self._get_cells(qx1, qy1, qx2, qy2):
            if cell in self.cells:
                candidates.update(self.cells[cell])

        # Exact AABB intersection filter
        results = set()
        for cid in candidates:
            bx1, by1, bx2, by2 = self.item_boxes[cid]
            if not (bx2 < qx1 or bx1 > qx2 or by2 < qy1 or by1 > qy2):
                results.add(cid)
        return results

    def clear(self):
        self.cells.clear()
        self.item_boxes.clear()


class IndexedPCBSnapshot:
    """Read-optimized, indexed representation of a PCB document state with domain revisions."""

    def __init__(self, raw_dump: Dict[str, Any], project_id: str = "", revision: str = "",
                 tracks: Optional[List[Dict[str, Any]]] = None,
                 vias: Optional[List[Dict[str, Any]]] = None,
                 zones: Optional[List[Dict[str, Any]]] = None,
                 stackup: Optional[Any] = None,
                 rules: Optional[Dict[str, Any]] = None):
        self.raw_dump = raw_dump
        self.project_id = project_id
        self.revision = revision
        self.created_at = time.time()

        self.tracks: List[Dict[str, Any]] = tracks or []
        self.vias: List[Dict[str, Any]] = vias or []
        self.zones: List[Dict[str, Any]] = zones or []
        self.stackup: Optional[Any] = stackup
        self.rules: Dict[str, Any] = rules or {}

        # Indices
        self.ref_to_comp: Dict[str, Dict[str, Any]] = {}
        self.id_to_comp: Dict[str, Dict[str, Any]] = {}
        self.comp_to_pads: Dict[str, List[Dict[str, Any]]] = {}
        self.pad_lookup: Dict[Tuple[str, str], Dict[str, Any]] = {}  # (ref, pad_num) -> pad
        self.net_to_endpoints: Dict[str, List[NetEndpoint]] = {}
        self.net_to_components: Dict[str, Set[str]] = {}
        self.layer_to_components: Dict[int, List[str]] = {1: [], 2: [], 11: [], 12: []}
        self.footprint_invariants: Dict[str, FootprintInvariant] = {}
        self.spatial_index = SpatialGridIndex(cell_size_mil=150.0)
        self.connectivity_graph: Optional[Any] = None

        # Domain revisions
        self.geometry_rev = ""
        self.connectivity_rev = ""
        self.stackup_rev = ""
        self.copper_rev = ""
        self.rules_rev = ""
        self.fingerprint = ""

        self._build_indices()
        self._compute_all_revisions()

    def _compute_all_revisions(self):
        # 1. Geometry Revision (positions, rotations, layers, tracks, vias)
        hg = hashlib.sha1()
        for ref in sorted(self.raw_dump.keys()):
            c = self.raw_dump[ref]
            if not isinstance(c, dict): continue
            hg.update(f"{ref}:{c.get('x',0):.1f}:{c.get('y',0):.1f}:{c.get('rot',0)}:{c.get('layer',1)}".encode("utf-8"))
        for t in sorted(self.tracks, key=lambda x: str(x.get("id", ""))):
            hg.update(f"{t.get('x1',0)}:{t.get('y1',0)}:{t.get('x2',0)}:{t.get('y2',0)}:{t.get('width',0)}:{t.get('layer',1)}".encode("utf-8"))
        for v in sorted(self.vias, key=lambda x: str(x.get("id", ""))):
            hg.update(f"{v.get('x',0)}:{v.get('y',0)}:{v.get('dia',0)}:{v.get('hole_dia',0)}".encode("utf-8"))
        self.geometry_rev = hg.hexdigest()[:16]

        # 2. Connectivity Revision (pad nets, track nets, via nets)
        hc = hashlib.sha1()
        for ref in sorted(self.raw_dump.keys()):
            c = self.raw_dump[ref]
            if not isinstance(c, dict): continue
            for p in sorted(c.get("pads", []), key=lambda x: str(x.get("num", ""))):
                hc.update(f"{ref}:{p.get('num','')}:{p.get('net','')}".encode("utf-8"))
        for t in sorted(self.tracks, key=lambda x: str(x.get("id", ""))):
            hc.update(f"trk:{t.get('id','')}:{t.get('net','')}".encode("utf-8"))
        for v in sorted(self.vias, key=lambda x: str(x.get("id", ""))):
            hc.update(f"via:{v.get('id','')}:{v.get('net','')}".encode("utf-8"))
        self.connectivity_rev = hc.hexdigest()[:16]

        # 3. Stackup Revision
        hs = hashlib.sha1()
        if self.stackup:
            hs.update(json.dumps(self.stackup, sort_keys=True, default=str).encode("utf-8"))
        self.stackup_rev = hs.hexdigest()[:16]

        # 4. Copper Revision
        hcp = hashlib.sha1()
        for z in sorted(self.zones, key=lambda x: str(x.get("id", ""))):
            hcp.update(f"{z.get('id','')}:{z.get('net','')}:{z.get('layer',1)}:{z.get('priority',1)}".encode("utf-8"))
        self.copper_rev = hcp.hexdigest()[:16]

        # 5. Rules Revision
        hr = hashlib.sha1()
        if self.rules:
            hr.update(json.dumps(self.rules, sort_keys=True).encode("utf-8"))
        self.rules_rev = hr.hexdigest()[:16]

        # Composite Fingerprint
        h_comp = hashlib.sha1(f"{self.geometry_rev}:{self.connectivity_rev}:{self.stackup_rev}:{self.copper_rev}:{self.rules_rev}".encode("utf-8"))
        self.fingerprint = h_comp.hexdigest()[:16]

    @staticmethod
    def _compute_fingerprint(dump: Dict[str, Any]) -> str:
        """Fast fallback fingerprint for raw dumps."""
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

        self.spatial_index.clear()
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
            rot_rad = math.radians(rot_deg)
            cos_a = math.cos(rot_rad)
            sin_a = math.sin(rot_rad)

            # Insert component bounding box into spatial index
            bbox = comp.get("bbox", [-50, 50, -50, 50])
            self.spatial_index.insert(ref, cx + bbox[0], cy + bbox[2], cx + bbox[1], cy + bbox[3])

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
                    px = cx + dx  # dump pad offsets are already in the board frame (QA-03)
                    py = cy + dy
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
        """Incrementally updates a single component's coordinates, layer, and affected net endpoints."""
        if ref not in self.ref_to_comp:
            return
        comp = self.ref_to_comp[ref]
        old_layer = comp.get("layer", 1)
        comp["x"] = x_mil
        comp["y"] = y_mil
        comp["rot"] = rot_deg
        comp["layer"] = layer

        # Update layer_to_components
        if old_layer in self.layer_to_components and ref in self.layer_to_components[old_layer]:
            self.layer_to_components[old_layer].remove(ref)
        if layer not in self.layer_to_components:
            self.layer_to_components[layer] = []
        if ref not in self.layer_to_components[layer]:
            self.layer_to_components[layer].append(ref)

        # Pad offsets are board-frame at the component's stored rotation: rotate by the delta only (QA-03).
        rot_rad = math.radians(float(rot_deg) - float(comp.get("rot", 0.0) or 0.0))
        cos_a = math.cos(rot_rad)
        sin_a = math.sin(rot_rad)

        # Update spatial index
        bbox = comp.get("bbox", [-50, 50, -50, 50])
        self.spatial_index.insert(ref, x_mil + bbox[0], y_mil + bbox[2], x_mil + bbox[1], y_mil + bbox[3])

        for p in comp.get("pads", []):
            num = str(p.get("num", ""))
            net = p.get("net")
            if not net or net not in self.net_to_endpoints:
                continue
            dx = p.get("dx", 0.0)
            dy = p.get("dy", 0.0)
            px = x_mil + dx * cos_a - dy * sin_a
            py = y_mil + dx * sin_a + dy * cos_a
            for ep in self.net_to_endpoints[net]:
                if ep.ref == ref and ep.pad_num == num:
                    ep.x_mil = px
                    ep.y_mil = py
                    ep.layer = layer if ep.is_smd else 11
                    break

        # Invalidate dependent graph and recalculate all domain revisions
        self.connectivity_graph = None
        self._compute_all_revisions()

    def add_component(self, ref: str, comp: Dict[str, Any]):
        """Incrementally adds a new component and indexes its pads and geometry."""
        from desk.component_intel import FootprintIntegrityEngine

        self.raw_dump[ref] = comp
        self.ref_to_comp[ref] = comp
        p_id = comp.get("id")
        if p_id:
            self.id_to_comp[str(p_id)] = comp

        pads = comp.get("pads", [])
        self.comp_to_pads[ref] = pads

        layer = comp.get("layer", 1)
        if layer not in self.layer_to_components:
            self.layer_to_components[layer] = []
        if ref not in self.layer_to_components[layer]:
            self.layer_to_components[layer].append(ref)

        cx = comp.get("x", 0.0)
        cy = comp.get("y", 0.0)
        rot_deg = comp.get("rot", 0.0) or 0.0
        rot_rad = math.radians(rot_deg)
        cos_a = math.cos(rot_rad)
        sin_a = math.sin(rot_rad)

        bbox = comp.get("bbox", [-50, 50, -50, 50])
        self.spatial_index.insert(ref, cx + bbox[0], cy + bbox[2], cx + bbox[1], cy + bbox[3])

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
                px = cx + dx  # board-frame offsets (QA-03)
                py = cy + dy
                is_smd = p.get("layer") not in (11, 12)

                self.net_to_endpoints[net].append(NetEndpoint(
                    ref=ref,
                    pad_num=num,
                    net=net,
                    x_mil=px,
                    y_mil=py,
                    layer=layer if is_smd else 11,
                    is_smd=is_smd,
                ))

        self.footprint_invariants[ref] = FootprintIntegrityEngine.extract_invariant(ref, comp)
        self.connectivity_graph = None
        self._compute_all_revisions()

    def remove_component(self, ref: str):
        """Incrementally removes a component, clearing pads and spatial indices."""
        if ref not in self.ref_to_comp:
            return
        comp = self.ref_to_comp.pop(ref, {})
        self.raw_dump.pop(ref, None)
        self.comp_to_pads.pop(ref, None)
        self.footprint_invariants.pop(ref, None)
        self.spatial_index.remove(ref)

        # Clear layer mapping
        for layer_list in self.layer_to_components.values():
            if ref in layer_list:
                layer_list.remove(ref)

        # Clear pad lookups and endpoints
        for p in comp.get("pads", []):
            num = str(p.get("num", ""))
            self.pad_lookup.pop((ref, num), None)
            net = p.get("net")
            if net and net in self.net_to_endpoints:
                self.net_to_endpoints[net] = [ep for ep in self.net_to_endpoints[net] if ep.ref != ref]
                if not self.net_to_endpoints[net]:
                    self.net_to_endpoints.pop(net, None)
            if net and net in self.net_to_components:
                self.net_to_components[net].discard(ref)
                if not self.net_to_components[net]:
                    self.net_to_components.pop(net, None)

        self.connectivity_graph = None
        self._compute_all_revisions()

    def update_pad_net(self, ref: str, pad_num: str, new_net: str):
        """Incrementally reassigns a pad's net connection."""
        if (ref, pad_num) not in self.pad_lookup:
            return
        pad = self.pad_lookup[(ref, pad_num)]
        old_net = pad.get("net") or ""
        pad["net"] = new_net

        # Remove old endpoint
        if old_net and old_net in self.net_to_endpoints:
            self.net_to_endpoints[old_net] = [
                ep for ep in self.net_to_endpoints[old_net]
                if not (ep.ref == ref and ep.pad_num == pad_num)
            ]
            if not self.net_to_endpoints[old_net]:
                self.net_to_endpoints.pop(old_net, None)
                self.net_to_components.pop(old_net, None)

        # Add new endpoint
        if new_net:
            comp = self.ref_to_comp.get(ref, {})
            cx = comp.get("x", 0.0)
            cy = comp.get("y", 0.0)
            rot_deg = comp.get("rot", 0.0) or 0.0
            rot_rad = math.radians(rot_deg)
            dx = pad.get("dx", 0.0)
            dy = pad.get("dy", 0.0)
            px = cx + dx  # board-frame offsets (QA-03)
            py = cy + dy
            is_smd = pad.get("layer") not in (11, 12)
            layer = comp.get("layer", 1)

            if new_net not in self.net_to_endpoints:
                self.net_to_endpoints[new_net] = []
                self.net_to_components[new_net] = set()
            self.net_to_components[new_net].add(ref)
            self.net_to_endpoints[new_net].append(NetEndpoint(
                ref=ref,
                pad_num=pad_num,
                net=new_net,
                x_mil=px,
                y_mil=py,
                layer=layer if is_smd else 11,
                is_smd=is_smd,
            ))

        self.connectivity_graph = None
        self._compute_all_revisions()

    def add_track(self, track_dict: Dict[str, Any]):
        """Incrementally adds a routed track segment."""
        self.tracks.append(track_dict)
        self._compute_all_revisions()

    def remove_track(self, track_idx_or_id: Any):
        """Incrementally removes a track segment by index or ID."""
        if isinstance(track_idx_or_id, int) and 0 <= track_idx_or_id < len(self.tracks):
            self.tracks.pop(track_idx_or_id)
        else:
            self.tracks = [t for t in self.tracks if t.get("id") != track_idx_or_id]
        self._compute_all_revisions()

    def add_via(self, via_dict: Dict[str, Any]):
        """Incrementally adds a via."""
        self.vias.append(via_dict)
        self._compute_all_revisions()

    def remove_via(self, via_idx_or_id: Any):
        """Incrementally removes a via by index or ID."""
        if isinstance(via_idx_or_id, int) and 0 <= via_idx_or_id < len(self.vias):
            self.vias.pop(via_idx_or_id)
        else:
            self.vias = [v for v in self.vias if v.get("id") != via_idx_or_id]
        self._compute_all_revisions()

    def update_zone(self, zone_dict: Dict[str, Any]):
        """Incrementally adds or updates a copper zone."""
        zid = zone_dict.get("id")
        replaced = False
        for i, z in enumerate(self.zones):
            if z.get("id") == zid:
                self.zones[i] = zone_dict
                replaced = True
                break
        if not replaced:
            self.zones.append(zone_dict)
        self._compute_all_revisions()

    def update_stackup(self, stackup: Any):
        """Incrementally updates layer stackup."""
        self.stackup = stackup
        self._compute_all_revisions()

    def update_rules(self, rules: Dict[str, Any]):
        """Incrementally updates design rule constraints."""
        self.rules = rules
        self._compute_all_revisions()


class PCBSnapshotCache:
    """Manages in-memory and persistent snapshots with multi-domain invalidation."""
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
