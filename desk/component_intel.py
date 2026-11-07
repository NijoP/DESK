"""Component Intelligence & Footprint Protection Engine for DESK.
Extracts deep component requirements from PCB dumps, block specifications,
and MPN pin libraries. Enforces immutable footprint invariants and performs
hierarchical component classification.
"""
import re
import math
from typing import Dict, List, Tuple, Optional, Any, Set
from desk.models import (
    ComponentRequirement,
    FootprintInvariant,
    PadGeometry,
    PadGeometry as PadSpec
)

# Classification RegExes
CONNECTOR_REGEX = re.compile(r"^(J|CN|CON|USB|P|T|TB|FPC|SMA|RJ45|HDR|TERM)\d+", re.I)
SCREW_TERMINAL_REGEX = re.compile(r"^(TB|TERM|SCREW|PHOENIX)\d+|.*(TERMINAL|SCREW|BARRIER|SPRING).*", re.I)
MOUNTING_HOLE_REGEX = re.compile(r"^(H|MH|HOLE|MTG)\d+", re.I)
BUTTON_SWITCH_REGEX = re.compile(r"^(SW|KEY|BTN|BUTTON)\d+", re.I)
DISPLAY_REGEX = re.compile(r"^(LCD|OLED|DISP|TFT|SCREEN)\d+", re.I)

PRIMARY_IC_REGEX = re.compile(r"^(U|IC)\d+", re.I)
MOSFET_TRANSISTOR_REGEX = re.compile(r"^(Q|MOS|FET|TR)\d+", re.I)
PASSIVE_REGEX = re.compile(r"^(R|C|L|FB|D|LED|F|RV|MOV)\d+", re.I)
CRYSTAL_REGEX = re.compile(r"^(Y|X|XTAL|OSC)\d+", re.I)
INDUCTOR_REGEX = re.compile(r"^L\d+", re.I)
DIODE_REGEX = re.compile(r"^(D|LED)\d+", re.I)
PROTECTION_REGEX = re.compile(r"^(ESD|TVS|F|FUSE|PTC)\d+|.*(USBLC|TPD|ESD|PRTR).*", re.I)

MIL = 39.37007874

class ComponentClassifier:
    """Classifies components into Mechanical Anchors, Primary ICs, Passives, and Special Electrical."""

    @staticmethod
    def classify(ref: str, mpn: str = "", footprint: str = "", roles: Optional[Dict[str, Any]] = None,
                 pad_count: int = 2, net_names: Optional[Set[str]] = None) -> str:
        roles = roles or {}
        ref_u = ref.upper()
        mpn_u = mpn.upper()
        fp_u = footprint.upper()
        nets = {n.upper() for n in (net_names or set())}

        # 1. Check explicit project role overrides
        if ref in roles.get("connectors", []): return "mechanical_anchor"
        if ref in roles.get("screw_terminals", []): return "screw_terminal"
        if ref in roles.get("mounting_holes", []): return "mounting_hole"
        if ref in roles.get("primary_ics", []): return "primary_ic"
        if ref in roles.get("special_electrical", []): return "special_electrical"
        if ref in roles.get("rf", []): return "special_electrical"

        # 2. Mechanical Anchors
        if MOUNTING_HOLE_REGEX.match(ref_u) or "HOLE" in fp_u or "MOUNT" in fp_u:
            return "mounting_hole"
        if SCREW_TERMINAL_REGEX.match(ref_u) or SCREW_TERMINAL_REGEX.match(mpn_u) or "TERMINAL" in fp_u:
            return "screw_terminal"
        if (CONNECTOR_REGEX.match(ref_u) or "CONN" in fp_u or "USB" in fp_u or "FPC" in fp_u or "HDR" in fp_u) \
                and ref not in roles.get("not_connectors", []):
            return "mechanical_anchor"
        if BUTTON_SWITCH_REGEX.match(ref_u) or DISPLAY_REGEX.match(ref_u):
            return "mechanical_anchor"

        # 3. Special Electrical
        if CRYSTAL_REGEX.match(ref_u) or "XTAL" in fp_u or "OSC" in mpn_u:
            return "crystal"
        if PROTECTION_REGEX.match(ref_u) or PROTECTION_REGEX.match(mpn_u) or ref in roles.get("esd", []):
            return "protection"
        # Kelvin sense / current sense resistors (typically R with RSENSE / CSENSE in net or low milliohms)
        if ref_u.startswith("R") and (any("SENSE" in n or "CURR" in n or "SHUNT" in n for n in nets) or "WSL" in mpn_u):
            return "current_sense"
        # Switching power inductors and converter ICs
        if INDUCTOR_REGEX.match(ref_u) and any("SW" in n or "LX" in n or "BOOST" in n or "BUCK" in n for n in nets):
            return "switching_power"

        # 4. Primary ICs & Active Devices
        if PRIMARY_IC_REGEX.match(ref_u) or MOSFET_TRANSISTOR_REGEX.match(ref_u) or pad_count >= 5:
            return "primary_ic"

        # 5. Supporting Passives
        if PASSIVE_REGEX.match(ref_u):
            if ref_u.startswith("C"):
                # Decoupling vs ordinary capacitor
                if any(re.search(r"VCC|VDD|3V3|5V|1V8|VBAT|VBUS", n) for n in nets) and any(re.search(r"GND|VSS", n) for n in nets):
                    return "decoupling_capacitor"
                return "capacitor"
            if ref_u.startswith("R"):
                return "resistor"
            if ref_u.startswith("L") or ref_u.startswith("FB"):
                return "inductor"
            if DIODE_REGEX.match(ref_u):
                return "diode"

        return "passive"

class FootprintIntegrityEngine:
    """Guarantees footprint geometry, pad numbering, and pin-to-net invariants."""

    @staticmethod
    def extract_invariant(ref: str, dump_part: Dict[str, Any]) -> FootprintInvariant:
        pads = dump_part.get("pads", [])
        fp_name = dump_part.get("fp") or ""
        pad_nums = []
        pad_positions = {}
        pad_dimensions = {}
        pad_shapes = {}
        drill_defs = {}

        for p in pads:
            num = str(p.get("num", ""))
            pad_nums.append(num)
            pad_positions[num] = (float(p.get("dx", 0.0)), float(p.get("dy", 0.0)))
            sz = p.get("shape")
            if isinstance(sz, list) and len(sz) > 2:
                pad_dimensions[num] = (float(sz[1]), float(sz[2]))
                pad_shapes[num] = str(sz[0])
            else:
                pad_dimensions[num] = (20.0, 20.0)
                pad_shapes[num] = "RECT"
            if "drill" in p:
                drill_defs[num] = float(p["drill"])

        # Estimate pitch (O(N log N) with sweep-line window)
        pitch_mm = 0.0
        if len(pad_positions) >= 2:
            pts = sorted(pad_positions.values(), key=lambda pt: pt[0])
            min_dist = float("inf")
            n_pts = len(pts)
            for i in range(n_pts):
                px, py = pts[i]
                for j in range(i + 1, min(i + 8, n_pts)):
                    if (pts[j][0] - px) / MIL >= min_dist:
                        break
                    d = math.hypot(px - pts[j][0], py - pts[j][1]) / MIL
                    if d > 0.05 and d < min_dist:
                        min_dist = d
            pitch_mm = round(min_dist, 3) if min_dist != float("inf") else 0.0

        return FootprintInvariant(
            ref=ref,
            footprint_name=fp_name,
            pad_count=len(pads),
            pad_numbers=pad_nums,
            pad_positions=pad_positions,
            pad_dimensions=pad_dimensions,
            pad_pitch_mm=pitch_mm,
            pad_shapes=pad_shapes,
            drill_definitions=drill_defs,
            pin1_pos_mil=pad_positions.get("1", pad_positions.get("A1", (0.0, 0.0))),
            electrical_orientation=float(dump_part.get("rot", 0.0) or 0.0)
        )

    @staticmethod
    def verify(invariant: FootprintInvariant, current_part: Dict[str, Any]) -> List[str]:
        cur_pads = current_part.get("pads", [])
        cur_nums = [str(p.get("num", "")) for p in cur_pads]
        cur_pos = {str(p.get("num", "")): (float(p.get("dx", 0.0)), float(p.get("dy", 0.0))) for p in cur_pads}
        return invariant.validate_invariance(len(cur_pads), cur_nums, cur_pos)

class ComponentIntelligenceExtractor:
    """Builds complete ComponentRequirement instances from PCB dump, block specs, and pin caches."""

    @staticmethod
    def extract_all(pcb_dump: Dict[str, Any], blocks: Optional[List[Dict[str, Any]]] = None,
                    roles: Optional[Dict[str, Any]] = None, heights: Optional[Dict[str, float]] = None) -> Dict[str, ComponentRequirement]:
        roles = roles or {}
        heights = heights or {}
        blocks = blocks or []

        # Build MPN and block role lookup
        mpn_map = {}
        block_role_map = {}
        for b in blocks:
            for p in b.get("parts", []):
                ref = p.get("ref")
                if ref:
                    mpn_map[ref] = p.get("mpn", "")
                    block_role_map[ref] = p.get("role", "")

        reqs = {}
        for ref, c in pcb_dump.items():
            if not ref or not isinstance(c, dict): continue
            pads_raw = c.get("pads", [])
            pads = []
            pad_to_net = {}
            net_set = set()
            drill_count = 0

            for p in pads_raw:
                num = str(p.get("num", ""))
                net = p.get("net") or ""
                pad_to_net[num] = net
                if net: net_set.add(net)

                sz = p.get("shape")
                w, h = (float(sz[1]), float(sz[2])) if isinstance(sz, list) and len(sz) > 2 and isinstance(sz[1], (int, float)) else (20.0, 20.0)
                shape_kind = str(sz[0]) if isinstance(sz, list) and len(sz) > 0 else "RECT"
                layer = p.get("layer", 1)
                drill = float(p.get("drill", 0.0) if "drill" in p else (12.0 if layer in (11, 12) else 0.0))
                if drill > 0: drill_count += 1

                pads.append(PadGeometry(
                    num=num,
                    net=net,
                    dx_mil=float(p.get("dx", 0.0)),
                    dy_mil=float(p.get("dy", 0.0)),
                    width_mil=w,
                    height_mil=h,
                    shape=shape_kind,
                    layer=layer,
                    drill_mil=drill,
                    plated=(drill > 0)
                ))

            bbox = c.get("bbox") or [0, 0, 0, 0]
            w_mm = round((bbox[1] - bbox[0]) / MIL, 3)
            h_mm = round((bbox[3] - bbox[2]) / MIL, 3)
            thick_mm = heights.get(ref, 1.0)
            mpn = mpn_map.get(ref, "")
            fp = c.get("fp") or ""

            cls = ComponentClassifier.classify(ref, mpn=mpn, footprint=fp, roles=roles, pad_count=len(pads), net_names=net_set)
            invariant = FootprintIntegrityEngine.extract_invariant(ref, c)

            # Determine polarity requirement
            polarity = None
            if cls in ("diode", "protection"): polarity = "ANODE_CATHODE"
            elif ref.upper().startswith("C") and "TANT" in fp.upper(): polarity = "POLARIZED_CAP"
            elif len(pads) > 2 and any(p.num in ("1", "A1") for p in pads): polarity = "PIN_1_INDEXED"

            req = ComponentRequirement(
                ref=ref,
                mpn=mpn,
                package=fp,
                footprint_id=fp,
                width_mm=w_mm,
                height_mm=h_mm,
                thickness_mm=thick_mm,
                pad_count=len(pads),
                pads=pads,
                pad_to_net=pad_to_net,
                pin1_position=invariant.pin1_pos_mil,
                polarity=polarity,
                drill_count=drill_count,
                plated_holes=(drill_count > 0),
                courtyard_rect_mm=(round(bbox[0]/MIL, 3), round(bbox[1]/MIL, 3), round(bbox[2]/MIL, 3), round(bbox[3]/MIL, 3)),
                height_restriction_mm=heights.get(ref),
                electrical_role=cls,
                verified=True,
                invariants=invariant
            )
            reqs[ref] = req

        return reqs
