"""Offline performance benchmark for the core DESK engines (roadmap increment I-10).

`tools/profile_perf.py projects/<P>` profiles a real project, but its input (`state/pcb_dump.json`) is git-ignored, so
the profile cannot run on a fresh clone or in CI. This module supplies a checked-in SYNTHETIC board and runs the same
core operations on it, offline:

* `generate_fixture()` builds a deterministic WATCH-sized board (an MCU, regulator, sensor, flash, connectors and
  passives; about 40 parts / 170 pads). No real project data. `tests/fixtures/perf/synth_board.json` is its output
  (a test keeps the two identical); `scale_fixture(fx, k)` tiles it k times to measure how each stage grows.
* `run_offline(fx)` times every stage that does real DESK work: a cold pass, `repeat` timed passes with
  tracemalloc OFF (tracemalloc slows allocation, so timing and memory are separate passes), then one pass with
  tracemalloc ON for per-stage peak Python allocation. It also reads the process peak RSS high-water mark after
  each stage.
* Stages that need EasyEDA or Freerouting (bridge discovery and connection, window verification, the Freerouting
  run, EasyEDA DRC) are listed under `not_measured` with the reason, never timed as no-ops.

Numbers depend on the host. A result is a measurement of THIS process on THIS machine and never a claim about a live
design. Pure standard library; Windows, Linux and macOS.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import statistics
import sys
import tempfile
import time
import tracemalloc
from typing import Any, Callable, Dict, List, Optional, Tuple

MIL = 39.37007874
FIXTURE_VERSION = 1
FIXTURE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "tests", "fixtures", "perf", "synth_board.json")
SHARED_NETS = ("GND", "3V3", "VBUS")

# Stages of tools/profile_perf.py that an offline run cannot measure, and why.
NOT_MEASURED = {
    "01_bridge_discovery": "needs the live EasyEDA bridge",
    "02_bridge_connection_establishment": "needs the live EasyEDA bridge",
    "03_window_document_verification": "needs a live EasyEDA window",
    "09_ratsnest_crossing_analysis": "computed inside 08_mst_computation by build_connectivity_graph; no separate call",
    "14_freerouting_execution": "external Java process (Freerouting); not run in CI",
    "16_drc_execution": "EasyEDA's own DRC engine; needs a live board",
}


# --------------------------------------------------------------------------------------------------------------------
# Synthetic board
# --------------------------------------------------------------------------------------------------------------------
def _rect_pad(num: Any, dx_mm: float, dy_mm: float, w_mm: float, h_mm: float, net: str, layer: int = 1) -> Dict[str, Any]:
    return {"num": str(num), "dx": round(dx_mm * MIL, 3), "dy": round(dy_mm * MIL, 3),
            "shape": ["RECT", round(w_mm * MIL, 3), round(h_mm * MIL, 3)], "rot": 0, "net": net, "layer": layer}


def _part(x_mm: float, y_mm: float, fp: str, pads: List[Dict[str, Any]], half_w_mm: float, half_h_mm: float,
          layer: int = 1) -> Dict[str, Any]:
    return {"x": round(x_mm * MIL, 3), "y": round(y_mm * MIL, 3), "rot": 0, "layer": layer, "fp": fp,
            "bbox": [round(-half_w_mm * MIL, 3), round(half_w_mm * MIL, 3), round(-half_h_mm * MIL, 3), round(half_h_mm * MIL, 3)],
            "pads": pads}


def _two_pin(x_mm: float, y_mm: float, fp: str, net1: str, net2: str, pitch_mm: float, pad_mm: Tuple[float, float]) -> Dict[str, Any]:
    pads = [_rect_pad(1, -pitch_mm / 2, 0, pad_mm[0], pad_mm[1], net1), _rect_pad(2, pitch_mm / 2, 0, pad_mm[0], pad_mm[1], net2)]
    return _part(x_mm, y_mm, fp, pads, pitch_mm / 2 + pad_mm[0] / 2, pad_mm[1] / 2)


def _dual_row(nets: List[str], pitch: float, row: float, pad: Tuple[float, float]) -> List[Dict[str, Any]]:
    out = []
    half = len(nets) // 2
    for n, net in enumerate(nets):
        col = n if n < half else len(nets) - 1 - n
        dx = -pitch * (half - 1) / 2 + col * pitch
        out.append(_rect_pad(n + 1, dx, row if n < half else -row, pad[0], pad[1], net))
    return out


def generate_fixture() -> Dict[str, Any]:
    """The deterministic synthetic benchmark board (no randomness, so every platform builds the same bytes)."""
    dump: Dict[str, Any] = {}

    # U1: MCU, QFN-48 7x7 mm, 0.5 mm pitch, exposed GND pad. Pins 1..48 counter-clockwise from the top-left.
    pads = []
    for i in range(48):
        pin = i + 1
        net = "GND" if pin % 12 in (0, 6) else ("3V3" if pin % 12 == 1 else f"MCU_IO{pin}")
        side, k = divmod(i, 12)
        off = -2.75 + k * 0.5
        dx, dy, w, h = {0: (-3.4, off, 0.8, 0.25), 1: (off, 3.4, 0.25, 0.8), 2: (3.4, -off, 0.8, 0.25), 3: (-off, -3.4, 0.25, 0.8)}[side]
        pads.append(_rect_pad(pin, dx, dy, w, h, net))
    pads.append(_rect_pad(49, 0, 0, 5.2, 5.2, "GND"))
    dump["U1"] = _part(25.0, 20.0, "QFN-48_7x7mm_P0.5mm", pads, 3.9, 3.9)

    # U2: LDO SOT-23-5 (VBUS -> 3V3)
    u2 = [("VBUS", -0.95, 1.1), ("GND", 0, 1.1), ("VBUS", 0.95, 1.1), ("NC_U2_4", 0.95, -1.1), ("3V3", -0.95, -1.1)]
    dump["U2"] = _part(8.0, 30.0, "SOT-23-5", [_rect_pad(n + 1, dx, dy, 0.6, 1.0, net) for n, (net, dx, dy) in enumerate(u2)], 1.5, 1.7)

    # U3: sensor LGA-8, U4: SPI flash SOIC-8; their signal pins land on MCU I/O nets.
    dump["U3"] = _part(38.0, 30.0, "LGA-8_2x2mm_P0.65mm",
                       _dual_row(["MCU_IO2", "MCU_IO3", "GND", "3V3", "MCU_IO4", "MCU_IO5", "GND", "3V3"], 0.65, 0.8, (0.35, 0.5)), 1.2, 1.2)
    dump["U4"] = _part(38.0, 10.0, "SOIC-8_3.9x4.9mm_P1.27mm",
                       _dual_row(["MCU_IO14", "MCU_IO15", "MCU_IO16", "GND", "MCU_IO17", "MCU_IO19", "MCU_IO20", "3V3"], 1.27, 2.7, (0.6, 1.5)), 3.1, 2.6)

    # J1: USB-C style receptacle (12 pads) on the left edge; J2: 6-pin 2.54 mm THT programming header.
    j1_nets = ["GND", "VBUS", "USB_CC1", "USB_DP", "USB_DN", "USB_SBU1", "USB_SBU2", "USB_DN", "USB_DP", "USB_CC2", "VBUS", "GND"]
    dump["J1"] = _part(3.0, 20.0, "USB-C_16P", [_rect_pad(n + 1, 0, -2.75 + n * 0.5, 1.2, 0.3, net) for n, net in enumerate(j1_nets)], 2.0, 4.5)
    j2_nets = ["3V3", "MCU_IO26", "MCU_IO27", "MCU_IO28", "MCU_IO29", "GND"]
    dump["J2"] = _part(47.0, 20.0, "PinHeader_1x06_P2.54mm",
                       [_rect_pad(n + 1, 0, -6.35 + n * 2.54, 1.7, 1.7, net, layer=11) for n, net in enumerate(j2_nets)], 1.3, 7.6)

    # Y1: 4-pad crystal on two MCU pins.
    y1 = [("MCU_IO31", -0.95, 0.75), ("GND", 0.95, 0.75), ("MCU_IO32", 0.95, -0.75), ("GND", -0.95, -0.75)]
    dump["Y1"] = _part(25.0, 30.0, "Crystal_3225", [_rect_pad(n + 1, dx, dy, 1.0, 0.9, net) for n, (net, dx, dy) in enumerate(y1)], 1.8, 1.4)

    # SW1: 4-pad tactile switch (reset), D1: LED, L1: input inductor, FB1: ferrite to the analog rail.
    sw = [("MCU_IO33", -2.0, 1.2), ("MCU_IO33", 2.0, 1.2), ("GND", -2.0, -1.2), ("GND", 2.0, -1.2)]
    dump["SW1"] = _part(14.0, 6.0, "SW_SPST_4P", [_rect_pad(n + 1, dx, dy, 1.0, 0.8, net) for n, (net, dx, dy) in enumerate(sw)], 2.6, 1.7)
    dump["D1"] = _two_pin(44.0, 34.0, "LED_0603", "LED_A", "GND", 1.6, (0.8, 0.8))
    dump["L1"] = _two_pin(8.0, 36.0, "L_0805", "VBUS_IN", "VBUS", 1.9, (1.0, 1.3))
    dump["FB1"] = _two_pin(8.0, 12.0, "FB_0603", "3V3", "3V3_A", 1.6, (0.8, 0.8))

    # 30 passives: decoupling around U1 / U2 / U3 / U4, pull-ups, series resistors, the LED resistor, CC resistors.
    passives = [
        ("C1", "C0402", "3V3", "GND", 21.0, 15.0), ("C2", "C0402", "3V3", "GND", 29.0, 15.0), ("C3", "C0402", "3V3", "GND", 21.0, 25.0),
        ("C4", "C0402", "3V3", "GND", 29.0, 25.0), ("C5", "C0603", "VBUS", "GND", 5.0, 33.0), ("C6", "C0603", "3V3", "GND", 11.0, 33.0),
        ("C7", "C0402", "3V3", "GND", 35.0, 33.0), ("C8", "C0402", "3V3", "GND", 41.0, 13.0), ("C9", "C0402", "MCU_IO31", "GND", 22.0, 33.0),
        ("C10", "C0402", "MCU_IO32", "GND", 28.0, 33.0), ("C11", "C0603", "3V3_A", "GND", 11.0, 12.0), ("C12", "C0402", "MCU_IO33", "GND", 17.0, 6.0),
        ("R1", "R0402", "USB_CC1", "GND", 6.0, 15.0), ("R2", "R0402", "USB_CC2", "GND", 6.0, 25.0), ("R3", "R0402", "USB_DP", "MCU_IO8", 12.0, 18.0),
        ("R4", "R0402", "USB_DN", "MCU_IO9", 12.0, 22.0), ("R5", "R0402", "3V3", "MCU_IO33", 17.0, 9.0), ("R6", "R0402", "3V3", "MCU_IO2", 35.0, 36.0),
        ("R7", "R0402", "3V3", "MCU_IO3", 38.0, 36.0), ("R8", "R0402", "MCU_IO35", "LED_A", 41.0, 34.0), ("R9", "R0402", "3V3", "MCU_IO14", 34.0, 6.0),
        ("R10", "R0402", "MCU_IO21", "3V3_A", 31.0, 6.0), ("R11", "R0402", "MCU_IO22", "GND", 28.0, 6.0), ("R12", "R0402", "MCU_IO23", "3V3", 25.0, 6.0),
        ("R13", "R0402", "MCU_IO10", "MCU_IO40", 19.0, 30.0), ("R14", "R0402", "MCU_IO11", "MCU_IO41", 31.0, 30.0), ("R15", "R0402", "MCU_IO44", "GND", 44.0, 6.0),
        ("R16", "R0402", "MCU_IO45", "3V3", 44.0, 9.0), ("R17", "R0402", "MCU_IO46", "GND", 15.0, 36.0), ("R18", "R0402", "VBUS_IN", "MCU_IO47", 3.0, 36.0),
    ]
    for ref, fp, n1, n2, x, y in passives:
        pitch, pad = ((1.0, (0.5, 0.55)) if "0402" in fp else (1.6, (0.8, 0.8)))
        dump[ref] = _two_pin(x, y, fp, n1, n2, pitch, pad)

    plan = {"board_mm": [50.0, 40.0], "origin_mm": [0, 0], "roles": {"connectors": ["J1", "J2"]}, "heights": {"J1": 3.2, "J2": 8.5}}
    return {"fixture_version": FIXTURE_VERSION, "name": "SYNTH_BENCH",
            "note": "Synthetic benchmark board generated by desk.perf_bench.generate_fixture(); not a real design.",
            "plan": plan, "dump": dict(sorted(dump.items()))}


def fixture_json(fx: Dict[str, Any]) -> str:
    """Canonical serialisation used for the checked-in fixture file."""
    return json.dumps(fx, indent=1, sort_keys=True) + "\n"


def load_fixture(path: Optional[str] = None) -> Dict[str, Any]:
    with open(path or FIXTURE_PATH, encoding="utf-8") as f:
        return json.load(f)


def scale_fixture(fx: Dict[str, Any], factor: int) -> Dict[str, Any]:
    """Tile the board `factor` times on a grid. Signal nets are copied per tile; GND / 3V3 / VBUS stay shared, so the
    power nets grow with the board the way they do on a real multi-block design."""
    factor = int(factor)
    if factor < 1:
        raise ValueError("scale factor must be >= 1")
    if factor == 1:
        return json.loads(json.dumps(fx))
    cols = 1
    while cols * cols < factor:
        cols += 1
    rows = (factor + cols - 1) // cols
    W, H = fx["plan"]["board_mm"]
    dump: Dict[str, Any] = {}
    for t in range(factor):
        cx, cy = (t % cols) * W, (t // cols) * H
        for ref, comp in fx["dump"].items():
            c = json.loads(json.dumps(comp))
            c["x"] = round(c["x"] + cx * MIL, 3)
            c["y"] = round(c["y"] + cy * MIL, 3)
            for p in c["pads"]:
                if p.get("net") and p["net"] not in SHARED_NETS:
                    p["net"] = f"{p['net']}_T{t}"
            dump[f"{ref}_T{t}"] = c
    plan = json.loads(json.dumps(fx["plan"]))
    plan["board_mm"] = [W * cols, H * rows]
    plan["roles"] = {"connectors": [f"{r}_T{t}" for t in range(factor) for r in fx["plan"].get("roles", {}).get("connectors", [])]}
    plan["heights"] = {f"{r}_T{t}": h for t in range(factor) for r, h in fx["plan"].get("heights", {}).items()}
    return {**fx, "name": f"{fx['name']}_x{factor}", "plan": plan, "dump": dump}


def board_counts(dump: Dict[str, Any]) -> Dict[str, int]:
    pads = [p for c in dump.values() for p in c.get("pads", [])]
    return {"components": len(dump), "pads": len(pads), "nets": len({p["net"] for p in pads if p.get("net")})}


def synthetic_ses(dump: Dict[str, Any]) -> str:
    """A Specctra SES whose network_out holds one wire per consecutive pad pair of every net, plus a via per net:
    the shape SESParser.parse_ses_copper reads after a Freerouting run."""
    nets: Dict[str, List[Tuple[float, float]]] = {}
    for comp in dump.values():
        for p in comp.get("pads", []):
            if p.get("net"):
                nets.setdefault(p["net"], []).append((comp["x"] + p.get("dx", 0.0), comp["y"] + p.get("dy", 0.0)))
    out = ["(session \"SYNTH_BENCH\"", " (routes", "  (resolution mil 1000)", "  (network_out"]
    for net in sorted(nets):
        pts = nets[net]
        if len(pts) < 2:
            continue
        out.append(f"   (net \"{net}\"")
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            out.append(f"    (wire (path TopLayer 8000 {int(x1 * 1000)} {int(y1 * 1000)} {int(x2 * 1000)} {int(y1 * 1000)} "
                       f"{int(x2 * 1000)} {int(y2 * 1000)}))")
        out.append(f"    (via \"Via[0-1]_24:12_mil\" {int(pts[0][0] * 1000)} {int(pts[0][1] * 1000)})")
        out.append("   )")
    out += ["  )", " )", ")"]
    return "\n".join(out) + "\n"


def synthetic_drc(dump: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Raw EasyEDA-shaped DRC rows: one clearance, one open-net and one drill row for every fourth net."""
    nets = sorted({p["net"] for c in dump.values() for p in c.get("pads", []) if p.get("net")})
    rows: List[Dict[str, Any]] = []
    for i, net in enumerate(nets[::4]):
        rows.append({"ruleName": "Clearance", "errorType": "TrackToTrack", "layer": "Top", "pos": [i * 10, i * 20],
                     "obj1": {"net": net}, "obj2": {"net": "GND"}})
        rows.append({"ruleName": "Unconnected", "errorType": "OpenNet", "layer": "Top", "pos": [i * 10 + 5, i * 20], "obj1": {"net": net}})
        rows.append({"ruleName": "HoleSize", "errorType": "MinDrill", "layer": "Multi", "pos": [i * 10, i * 20 + 5], "obj1": {"net": net}})
    return rows


# --------------------------------------------------------------------------------------------------------------------
# Memory readings
# --------------------------------------------------------------------------------------------------------------------
def peak_rss_mb() -> Optional[float]:
    """Peak resident set size of THIS process in MB (Linux/macOS ru_maxrss, Windows PeakWorkingSetSize); None when the
    platform gives no cheap reading. A high-water mark: it never goes down."""
    try:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes

            class PMC(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t),
                            ("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
                            ("PeakPagefileUsage", ctypes.c_size_t)]
            pmc = PMC()
            pmc.cb = ctypes.sizeof(PMC)
            k32 = ctypes.WinDLL("kernel32")
            k32.GetCurrentProcess.restype = wintypes.HANDLE
            psapi = ctypes.WinDLL("psapi")
            psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
            if psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb):
                return round(pmc.PeakWorkingSetSize / (1024 * 1024), 2)
            return None
        import resource
        ru = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return round(ru / (1024 * 1024), 2) if sys.platform == "darwin" else round(ru / 1024.0, 2)
    except Exception:
        return None


# --------------------------------------------------------------------------------------------------------------------
# Stages
# --------------------------------------------------------------------------------------------------------------------
Stage = Tuple[str, Callable[[Dict[str, Any]], Any]]

STAGE_NAMES = (
    "04_pcb_component_extraction", "05_pad_extraction", "06_footprint_invariant_validation",
    "07_connectivity_graph_construction", "08_mst_computation", "10_placement_generation",
    "11_placement_validation", "12_dsn_generation", "13_dsn_tuning", "15_ses_import_and_parse",
    "17_drc_parsing", "18_recovery_planning", "19_state_persistence",
)


def _stages() -> List[Stage]:
    """The offline core operations, in pipeline order (STAGE_NAMES). Each reads and writes the shared `ctx` dict."""
    from desk.component_intel import ComponentIntelligenceExtractor, FootprintIntegrityEngine
    from desk.drc_engine import DRCParser, RecoveryPlanner
    from desk.placement_intel import PlacementIntelligenceEngine
    from desk.routability import PlacementAcceptanceGate, RoutabilityEvaluator
    from desk.router import DSNTuningEngine
    from desk.routing.connectivity import SESParser
    from desk.routing.dsn_fixture import tiny_board_dsn
    from desk import ledger as LG
    from desk import placement

    def s04(ctx):
        ctx["comp_records"] = {k: {ck: cv for ck, cv in v.items() if ck != "pads"} for k, v in ctx["dump"].items()}

    def s05(ctx):
        ctx["pad_records"] = {k: v.get("pads", []) for k, v in ctx["dump"].items()}

    def s06(ctx):
        dump = ctx["dump"]
        inv = {k: FootprintIntegrityEngine.extract_invariant(k, v) for k, v in dump.items()}
        for k, i in inv.items():
            FootprintIntegrityEngine.verify(i, dump[k])

    def s07(ctx):
        eps: Dict[str, list] = {}
        for ref, comp in ctx["dump"].items():
            for p in comp.get("pads", []):
                if p.get("net"):
                    eps.setdefault(p["net"], []).append((ref, p.get("num"), p.get("dx", 0), p.get("dy", 0)))
        ctx["net_endpoints"] = eps

    def s08(ctx):
        ctx["graph"] = RoutabilityEvaluator.build_connectivity_graph(ctx["dump"])

    def s10(ctx):
        plan = ctx["plan"]
        ctx["reqs"] = ComponentIntelligenceExtractor.extract_all(ctx["dump"], blocks=[], roles=plan.get("roles", {}),
                                                                 heights=plan.get("heights", {}))
        PlacementIntelligenceEngine(tuple(plan["board_mm"])).generate_hierarchical_placement(ctx["reqs"], blocks=[])

    def s11(ctx):
        E, W, _ = placement.check(ctx["dump"], ctx["plan"], [])
        PlacementAcceptanceGate.evaluate(ctx["dump"], {}, ctx["reqs"], tuple(ctx["plan"]["board_mm"]),
                                         standard_errors=E, standard_warnings=W)

    def s12(ctx):
        W, H = ctx["plan"]["board_mm"]
        ctx["dsn"] = tiny_board_dsn(width_mm=W, height_mm=H, nets=max(1, ctx["counts"]["nets"]))

    def s13(ctx):
        W, H = ctx["plan"]["board_mm"]
        DSNTuningEngine.tune_dsn(ctx["dsn"], (W * MIL, H * MIL), power_nets=set(SHARED_NETS))

    def s15(ctx):
        ctx["tracks"], ctx["vias"] = SESParser.parse_ses_copper(ctx["ses"])

    def s17(ctx):
        ctx["violations"] = DRCParser.parse(ctx["drc_raw"])

    def s18(ctx):
        RecoveryPlanner.plan_recovery(1, ctx["violations"])

    def s19(ctx):
        LG.add(ctx["ledger_dir"], "fact", "synthetic benchmark record", source="desk.perf_bench")
        LG.read(ctx["ledger_dir"])

    return list(zip(STAGE_NAMES, (s04, s05, s06, s07, s08, s10, s11, s12, s13, s15, s17, s18, s19)))


def _pass(stages: List[Stage], base: Dict[str, Any], tmp_root: str, idx: int, trace: bool) -> Dict[str, Dict[str, Any]]:
    ctx = dict(base)
    ctx["ledger_dir"] = os.path.join(tmp_root, f"pass{idx}")
    os.makedirs(ctx["ledger_dir"], exist_ok=True)
    out: Dict[str, Dict[str, Any]] = {}
    for name, fn in stages:
        before = 0
        if trace:
            tracemalloc.reset_peak()
            before, _ = tracemalloc.get_traced_memory()
        c0, w0 = time.process_time(), time.perf_counter()
        fn(ctx)
        w1, c1 = time.perf_counter(), time.process_time()
        rec: Dict[str, Any] = {"wall_ms": (w1 - w0) * 1000.0, "cpu_ms": (c1 - c0) * 1000.0}
        if trace:
            _, peak = tracemalloc.get_traced_memory()
            rec["peak_traced_kb"] = max(0.0, (peak - before) / 1024.0)
            rec["rss_high_water_mb"] = peak_rss_mb()
        out[name] = rec
    return out


def run_offline(fx: Dict[str, Any], repeat: int = 5) -> Dict[str, Any]:
    """Measure every offline stage on board `fx`. Returns medians over `repeat` timed passes, the cold first pass,
    per-stage peak traced allocation and the process peak RSS. Never touches the network or a project directory
    (the state-persistence stage writes its ledger into a temporary directory that is removed afterwards)."""
    repeat = max(1, int(repeat))
    t_import = time.perf_counter()
    stages = _stages()
    import_ms = (time.perf_counter() - t_import) * 1000.0
    dump, plan = fx["dump"], fx["plan"]
    counts = board_counts(dump)
    base = {"dump": dump, "plan": plan, "counts": counts, "ses": synthetic_ses(dump), "drc_raw": synthetic_drc(dump)}
    rss_start = peak_rss_mb()
    was_tracing = tracemalloc.is_tracing()
    if was_tracing:
        tracemalloc.stop()
    tmp_root = tempfile.mkdtemp(prefix="desk_perf_")
    try:
        t_cold = time.perf_counter()
        cold = _pass(stages, base, tmp_root, 0, trace=False)
        cold_total_ms = (time.perf_counter() - t_cold) * 1000.0
        warm = [_pass(stages, base, tmp_root, i + 1, trace=False) for i in range(repeat)]
        tracemalloc.start()
        try:
            mem = _pass(stages, base, tmp_root, repeat + 1, trace=True)
        finally:
            tracemalloc.stop()
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
        if was_tracing:
            tracemalloc.start()

    result_stages: Dict[str, Dict[str, Any]] = {}
    for name, _ in stages:
        walls = sorted(p[name]["wall_ms"] for p in warm)
        result_stages[name] = {
            "median_wall_ms": round(statistics.median(walls), 4),
            "min_wall_ms": round(walls[0], 4),
            "max_wall_ms": round(walls[-1], 4),
            "median_cpu_ms": round(statistics.median(p[name]["cpu_ms"] for p in warm), 4),
            "cold_wall_ms": round(cold[name]["wall_ms"], 4),
            "peak_traced_kb": round(mem[name]["peak_traced_kb"], 1),
            "rss_high_water_mb": mem[name]["rss_high_water_mb"],
        }
    total = sum(s["median_wall_ms"] for s in result_stages.values())
    ranking = sorted(result_stages, key=lambda n: result_stages[n]["median_wall_ms"], reverse=True)
    return {
        "fixture": fx.get("name"), "fixture_version": fx.get("fixture_version"), "counts": counts, "repeat": repeat,
        "stages": result_stages,
        "sum_median_wall_ms": round(total, 4),
        "cold_pipeline_wall_ms": round(cold_total_ms, 4),
        "engine_import_ms": round(import_ms, 3),
        "hotspots": [{"stage": n, "median_wall_ms": result_stages[n]["median_wall_ms"],
                      "share": round(result_stages[n]["median_wall_ms"] / total, 4) if total else 0.0} for n in ranking],
        "stages_over_10ms": [n for n in ranking if result_stages[n]["median_wall_ms"] >= 10.0],
        "peak_rss_mb_before": rss_start, "peak_rss_mb_after": peak_rss_mb(),
        "not_measured": dict(NOT_MEASURED),
    }


def host_info() -> Dict[str, Any]:
    info: Dict[str, Any] = {"platform": sys.platform, "system": platform.system(), "release": platform.release(),
                            "machine": platform.machine(), "python": platform.python_version(),
                            "implementation": platform.python_implementation(), "cpu_count": os.cpu_count()}
    try:
        from desk.runtime.resource_profile import ResourceDetector
        hw = ResourceDetector.detect()
        info.update({"physical_ram_mb": hw.physical_ram_mb, "resource_tier": hw.resource_tier})
    except Exception:
        pass
    return info


def format_table(res: Dict[str, Any]) -> str:
    """A Markdown table of one run (used for the CI job summary and the terminal)."""
    c = res["counts"]
    lines = [f"**{res['fixture']}**: {c['components']} components, {c['pads']} pads, {c['nets']} nets; "
             f"median of {res['repeat']} warm passes", "",
             "| Stage | median ms | min ms | max ms | cold ms | CPU ms | peak traced KB | RSS high-water MB |",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for name, s in sorted(res["stages"].items(), key=lambda kv: kv[1]["median_wall_ms"], reverse=True):
        lines.append(f"| {name} | {s['median_wall_ms']:.3f} | {s['min_wall_ms']:.3f} | {s['max_wall_ms']:.3f} | "
                     f"{s['cold_wall_ms']:.3f} | {s['median_cpu_ms']:.3f} | {s['peak_traced_kb']:.1f} | {s['rss_high_water_mb']} |")
    lines.append(f"| **sum of medians** | **{res['sum_median_wall_ms']:.3f}** | | | {res['cold_pipeline_wall_ms']:.3f} | | | "
                 f"{res['peak_rss_mb_after']} |")
    return "\n".join(lines)
