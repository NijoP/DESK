"""Minimal Specctra DSN generator for engine smoke tests and fixtures (rework items B/C).

Produces a small, valid, routable board in the exact dialect EasyEDA Pro exports (one image `u1`
holding every pad, padstacks as polygons, one class per net, closed boundary, optional planes and
keep-outs). Freerouting routes it to 100 % in seconds, which is how DESK proves on a host that the
installed engine starts, routes and WRITES a SES before any long run (KF-20261111-006).

Zero external dependencies.
"""
from __future__ import annotations
from typing import Dict, List, Optional, Sequence, Tuple

MIL = 39.37007874


def _pad_polygon(layer: str, w: float, h: float) -> str:
    hw, hh = w / 2.0, h / 2.0
    return f"(polygon {layer} 0.1 {hw:.2f} {-hh:.2f} {-hw:.2f} {-hh:.2f} {-hw:.2f} {hh:.2f} {hw:.2f} {hh:.2f} {hw:.2f} {-hh:.2f})"


def tiny_board_dsn(width_mm: float = 20.0, height_mm: float = 20.0, nets: int = 4, layers: int = 2,
                   planes: Optional[List[Dict]] = None, keepouts_mil: Optional[List[Tuple[str, Sequence[float]]]] = None,
                   pad_mil: float = 30.0, pitch_mm: float = 2.54) -> str:
    """A board with `nets` two-pin nets: pad A of net i on the left column, pad B on the right column,
    staggered so the ratsnest crosses nothing. Coordinates in mil, DSN y axis as EasyEDA exports it."""
    W, H = width_mm * MIL, height_mm * MIL
    layer_names = ["TopLayer", "BottomLayer"] if layers == 2 else ["TopLayer", "Inner1", "Inner2", "BottomLayer"]
    lines: List[str] = []
    a = lines.append
    a("(PCB\n  \"DESK_SMOKE\"\n  (parser\n    (host_cad \"DESK\")\n    (host_version \"fixture\")\n  )\n  (resolution mil 1000)\n  (structure")
    a(f"    (boundary (path signal 0 0 0 0 {H:.2f} {W:.2f} {H:.2f} {W:.2f} 0 0 0))")
    a("    (via via0)\n    (grid via 1.25)\n    (grid wire 1.25)\n    (grid place 0.25)")
    a("    (rule (clear 4.05))\n    (rule (clear 4.05 (type default_smd)))\n    (rule (clear 4.05 (type smd_smd)))\n    (rule (width 5.00))")
    for ln in layer_names:
        a(f"    (layer {ln} (type signal))")
    for name, rect in (keepouts_mil or []):
        x0, y0, x1, y1 = rect
        a(f"    (keepout\n      \"{name}\"\n      (polygon signal 0 {x0:.2f} {y0:.2f} {x1:.2f} {y0:.2f} {x1:.2f} {y1:.2f} {x0:.2f} {y1:.2f})\n    )")
    for pl in planes or []:
        pts = " ".join(f"{x * MIL:.2f} {y * MIL:.2f}" for x, y in pl["polygon_mm"])
        a(f"    (plane {pl['net']} (polygon {pl['layer']} 0 {pts}))")
    a("  )\n  (placement\n    (component u1 (place u1 0 0 front 0))\n  )\n  (library\n    (image\n      u1")
    pins: Dict[str, List[str]] = {}
    pad_ids: List[Tuple[str, float, float]] = []
    x_left, x_right = 4.0 * MIL, (width_mm - 4.0) * MIL
    for i in range(nets):
        y = (3.0 + i * pitch_mm) * MIL
        if y > H - 3.0 * MIL:
            break
        net = f"N{i + 1}"
        pa, pb = f"{i + 1:02d}a0000000000{i + 1:02d}", f"{i + 1:02d}b0000000000{i + 1:02d}"
        pad_ids += [(pa, x_left, y), (pb, x_right, y + 0.5 * MIL)]
        pins[net] = [f"u1-{pa}", f"u1-{pb}"]
    for pid, x, y in pad_ids:
        a(f"      (pin psmd {pid} {x:.2f} {y:.2f})")
    a("    )")
    a(f"    (padstack\n      psmd\n      (shape\n        {_pad_polygon('TopLayer', pad_mil, pad_mil)}\n      )\n      (attach off)\n    )")
    a("    (padstack\n      via0\n" + "".join(f"      (shape (circle {ln} 24))\n" for ln in layer_names) + "    )")
    a("  )\n  (network")
    for net, plist in pins.items():
        a(f"    (net {net} (pins {' '.join(plist)}))")
    for net in pins:
        a(f"    (class {net} {net}\n      (circuit (use_via via0))\n      (rule (width 8.00) (clearance 4.05))\n    )")
    a("  )\n  (wiring\n  )\n)")
    return "\n".join(lines) + "\n"
