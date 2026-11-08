"""EasyEDA Pro PCB Adapter.
Provides deterministic, batch-oriented interfaces for:
- Complete PCB primitive readback (components, pads, tracks, vias, outline, zones, poured regions, stackup, DRC rules)
- Copper zone creation and modification
- Net and layer assignment
- Repour triggering
- Readback verification

NOTE: Methods communicating directly with the live bridge are marked:
STATUS = "NOT_LIVE_VERIFIED"
until live verification is performed on a disposable project.

Zero external dependencies (pure Python standard library).
"""
import json
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Tuple

MIL = 39.37007874

@dataclass
class PCBReadbackData:
    project_name: str
    pcb_uuid: str
    components: Dict[str, Any] = field(default_factory=dict)
    tracks: List[Dict[str, Any]] = field(default_factory=list)
    vias: List[Dict[str, Any]] = field(default_factory=list)
    zones: List[Dict[str, Any]] = field(default_factory=list)
    poured_regions: List[Dict[str, Any]] = field(default_factory=list)
    stackup_config: Optional[Dict[str, Any]] = None
    net_classes: List[Dict[str, Any]] = field(default_factory=list)
    diff_pairs: List[Dict[str, Any]] = field(default_factory=list)
    raw_status: str = "OFFLINE_EXTRACTED"

class EasyEDAPcbAdapter:
    """Batch-oriented adapter for EasyEDA Pro PCB inspection, copper zones, and DRC queries."""

    STATUS_READBACK = "IMPLEMENTED_AND_TESTED_OFFLINE"
    STATUS_COPPER_MUTATION = "NOT_LIVE_VERIFIED"
    STATUS_REPOUR = "NOT_LIVE_VERIFIED"

    def __init__(self, bridge_executor=None):
        """bridge_executor is an optional callable(js_code: str, window_id: str, timeout: int) -> dict"""
        self.executor = bridge_executor

    @staticmethod
    def build_batch_readback_script(pcb_uuid: str) -> str:
        """Constructs a high-performance single-roundtrip JS payload to extract all board primitives."""
        return f"""
        let __D = await eda.dmt_SelectControl.getCurrentDocumentInfo();
        if (!__D || __D.uuid !== "{pcb_uuid}") {{
            await eda.dmt_EditorControl.openDocument("{pcb_uuid}");
            await new Promise(r => setTimeout(r, 600));
            __D = await eda.dmt_SelectControl.getCurrentDocumentInfo();
        }}
        if (!__D || __D.uuid !== "{pcb_uuid}") return {{error: "WRONG SHEET", active: __D && __D.uuid}};

        // 1. Components and Pads
        const compIds = await eda.pcb_PrimitiveComponent.getAllPrimitiveId() || [];
        const comps = await eda.pcb_PrimitiveComponent.get(compIds) || [];
        const compOut = {{}};
        for (const c of comps) {{
            const id = c.getState_PrimitiveId();
            const des = c.getState_Designator();
            const x = c.getState_X(), y = c.getState_Y();
            const pads = await eda.pcb_PrimitiveComponent.getAllPinsByPrimitiveId(id) || [];
            compOut[des] = {{
                id: id,
                x: x,
                y: y,
                rot: c.getState_Rotation(),
                layer: c.getState_Layer(),
                footprint: (c.getState_Footprint() || {{}}).name || "",
                pads: pads.map(p => ({{
                    num: p.getState_PadNumber(),
                    x: p.getState_X(),
                    y: p.getState_Y(),
                    shape: p.getState_Pad(),
                    rot: p.getState_Rotation(),
                    net: p.getState_Net(),
                    layer: p.getState_Layer()
                }}))
            }};
        }}

        // 2. Tracks (Lines)
        const lines = await eda.pcb_PrimitiveLine.getAll() || [];
        const lineOut = lines.map(l => ({{
            id: l.getState_PrimitiveId(),
            x1: l.getState_StartX(),
            y1: l.getState_StartY(),
            x2: l.getState_EndX(),
            y2: l.getState_EndY(),
            width: l.getState_LineWidth(),
            layer: l.getState_Layer(),
            net: l.getState_Net()
        }}));

        // 3. Vias
        const vias = await eda.pcb_PrimitiveVia.getAll() || [];
        const viaOut = vias.map(v => ({{
            id: v.getState_PrimitiveId(),
            x: v.getState_X(),
            y: v.getState_Y(),
            hole_dia: v.getState_HoleDiameter(),
            dia: v.getState_Diameter(),
            net: v.getState_Net()
        }}));

        // 4. Copper Pour Zones
        const pours = await eda.pcb_PrimitivePour.getAll() || [];
        const pourOut = pours.map(p => ({{
            id: p.getState_PrimitiveId(),
            name: p.getState_PourName ? p.getState_PourName() : "",
            net: p.getState_Net(),
            layer: p.getState_Layer(),
            priority: p.getState_PourPriority ? p.getState_PourPriority() : 1,
            fill_method: p.getState_PourFillMethod ? p.getState_PourFillMethod() : 1,
            line_width: p.getState_LineWidth ? p.getState_LineWidth() : 10.0
        }}));

        // 5. Poured Copper Regions
        const poured = await eda.pcb_PrimitivePoured.getAll() || [];
        const pouredOut = poured.map(pr => ({{
            id: pr.getState_PrimitiveId(),
            net: pr.getState_Net(),
            layer: pr.getState_Layer()
        }}));

        // 6. Stackup Configuration
        let stackup = null;
        try {{
            stackup = await eda.pcb_Layer.getCurrentPhysicalStackingConfiguration();
        }} catch(e) {{}}

        // 7. DRC Net Classes & Diff Pairs
        let netClasses = [];
        let diffPairs = [];
        try {{
            netClasses = await eda.pcb_Drc.getAllNetClasses() || [];
            diffPairs = await eda.pcb_Drc.getAllDifferentialPairs() || [];
        }} catch(e) {{}}

        return {{
            ok: true,
            components: compOut,
            tracks: lineOut,
            vias: viaOut,
            zones: pourOut,
            poured_regions: pouredOut,
            stackup: stackup,
            net_classes: netClasses,
            diff_pairs: diffPairs
        }};
        """

    @staticmethod
    def build_create_zone_script(pcb_uuid: str,
                                 net: str,
                                 layer: int,
                                 points_mil: List[Tuple[float, float]],
                                 name: str = "ZONE",
                                 priority: int = 1,
                                 pour_fill_method: int = 1,
                                 spoke_width_mil: float = 12.0) -> str:
        """Constructs JS mutation to synthesize polygon and create copper pour zone.
        STATUS: NOT_LIVE_VERIFIED.
        """
        # Format polygon vertices into EasyEDA MathPolygon source format
        # Polygon source format: [x1, y1, 'L', x2, y2, x3, y3, ..., x1, y1]
        coords = []
        if len(points_mil) >= 3:
            coords.append(points_mil[0][0])
            coords.append(points_mil[0][1])
            coords.append('L')
            for pt in points_mil[1:]:
                coords.append(pt[0])
                coords.append(pt[1])
            # Close polygon
            coords.append(points_mil[0][0])
            coords.append(points_mil[0][1])
        else:
            raise ValueError("Polygon requires at least 3 vertices")

        poly_json = json.dumps(coords)

        return f"""
        let __D = await eda.dmt_SelectControl.getCurrentDocumentInfo();
        if (!__D || __D.uuid !== "{pcb_uuid}") {{
            await eda.dmt_EditorControl.openDocument("{pcb_uuid}");
            await new Promise(r => setTimeout(r, 600));
            __D = await eda.dmt_SelectControl.getCurrentDocumentInfo();
        }}
        if (!__D || __D.uuid !== "{pcb_uuid}") return {{error: "WRONG SHEET", active: __D && __D.uuid}};

        const polyCoords = {poly_json};
        const poly = await eda.pcb_MathPolygon.createPolygon(polyCoords);
        if (!poly) return {{error: "Failed to create polygon geometry"}};

        const pour = await eda.pcb_PrimitivePour.create(
            "{net}",
            {layer},
            poly,
            {pour_fill_method},
            false,
            "{name}",
            {priority},
            {spoke_width_mil},
            false
        );

        if (!pour) return {{error: "Failed to create copper pour zone"}};
        const id = pour.getState_PrimitiveId();
        return {{ok: true, primitive_id: id, net: "{net}", layer: {layer}, name: "{name}"}};
        """

    @staticmethod
    def build_modify_zone_script(pcb_uuid: str, primitive_id: str, updates: Dict[str, Any]) -> str:
        """Constructs JS mutation to modify copper zone properties.
        STATUS: NOT_LIVE_VERIFIED.
        """
        updates_json = json.dumps(updates)
        return f"""
        let __D = await eda.dmt_SelectControl.getCurrentDocumentInfo();
        if (!__D || __D.uuid !== "{pcb_uuid}") {{
            await eda.dmt_EditorControl.openDocument("{pcb_uuid}");
            await new Promise(r => setTimeout(r, 600));
            __D = await eda.dmt_SelectControl.getCurrentDocumentInfo();
        }}
        if (!__D || __D.uuid !== "{pcb_uuid}") return {{error: "WRONG SHEET", active: __D && __D.uuid}};

        const res = await eda.pcb_PrimitivePour.modify("{primitive_id}", {updates_json});
        if (!res) return {{error: "Failed to modify copper zone", primitive_id: "{primitive_id}"}};
        return {{ok: true, primitive_id: "{primitive_id}"}};
        """

    @staticmethod
    def build_repour_all_script(pcb_uuid: str) -> str:
        """Constructs JS mutation to rebuild copper regions for all copper pour zones.
        STATUS: NOT_LIVE_VERIFIED.
        """
        return f"""
        let __D = await eda.dmt_SelectControl.getCurrentDocumentInfo();
        if (!__D || __D.uuid !== "{pcb_uuid}") {{
            await eda.dmt_EditorControl.openDocument("{pcb_uuid}");
            await new Promise(r => setTimeout(r, 600));
            __D = await eda.dmt_SelectControl.getCurrentDocumentInfo();
        }}
        if (!__D || __D.uuid !== "{pcb_uuid}") return {{error: "WRONG SHEET", active: __D && __D.uuid}};

        const pours = await eda.pcb_PrimitivePour.getAll() || [];
        const results = [];
        for (const p of pours) {{
            const pid = p.getState_PrimitiveId();
            try {{
                const poured = await p.rebuildCopperRegion();
                results.push({{id: pid, ok: !!poured}});
            }} catch(e) {{
                results.push({{id: pid, ok: false, error: String(e)}});
            }}
        }}
        return {{ok: true, repoured_count: results.filter(r => r.ok).length, total: results.length, details: results}};
        """

    def parse_readback_payload(self, project_name: str, pcb_uuid: str, payload: Dict[str, Any]) -> PCBReadbackData:
        """Parses batch readback payload into structured PCBReadbackData dataclass."""
        if not payload or not payload.get("ok"):
            raise ValueError(f"Invalid readback payload: {payload.get('error', 'Unknown error')}")

        return PCBReadbackData(
            project_name=project_name,
            pcb_uuid=pcb_uuid,
            components=payload.get("components", {}),
            tracks=payload.get("tracks", []),
            vias=payload.get("vias", []),
            zones=payload.get("zones", []),
            poured_regions=payload.get("poured_regions", []),
            stackup_config=payload.get("stackup"),
            net_classes=payload.get("net_classes", []),
            diff_pairs=payload.get("diff_pairs", []),
            raw_status="PARSED_OK"
        )
