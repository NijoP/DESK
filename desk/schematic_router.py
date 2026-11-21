"""In-block schematic wire router and geometric checker for the `subsystem` wiring policy (docs/02_SCHEMATIC_STYLE.md).

Input: the pin tips of one placed block (absolute EasyEDA schematic coordinates + pin rotation, as read back after the
parts are placed) and the net class of every net (`desk.spec.classify_nets`). Output: a drawing plan of 2-point wire
segments and net labels that `desk.schematic_io.subsystem_draw_js` turns into EasyEDA calls.

    power  (rails, ground)          stub + net label on every pin, exactly as the `labels` style (power-symbol style)
    single (one pin, no port)       stub + net label (lint already flags it unless it is a port)
    local  (>= 2 pins, this block)  orthogonal wires between the pins, no label needed
    port / cross (block interface)  orthogonal wires between the in-block pins + ONE labelled stub: the label is the
                                    interface; it supplements the wires and never replaces them

Router: A* on the schematic grid (GRID units), one net at a time, shortest nets first; a branch leaves a pin in its
outward direction and joins the net's tree at its nearest point. Hard rules: a wire never enters a part body, a pin
tip (except its own end point), a cell owned by another net (wire, stub, label text) or another net's escape cell, so
different nets never cross, touch or overlap. A wire that joins the middle of a segment splits that segment, so every
junction is a shared end point. A net that cannot be routed inside the window falls back to labels (still
netlist-correct) and is reported in `plan["fallback"]`; the whole plan is then re-routed so the fallback stubs are
reserved before any wire. Deterministic: same input -> identical plan. Standard library only.

`check_plan` is the independent geometric checker (zero crossings, zero shorts, junctions only at end points, every
label on a wire end, every spec net connected and no two nets merged) and `derive_netlist` gives the netlist the
drawing implies, so both wiring styles can be proven equal to the spec offline.
"""
from __future__ import annotations

import heapq
import math
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

GRID = 10                       # schematic grid used for wires (EasyEDA symbol pin pitch)
BEND_COST = 4                   # extra cost per corner: prefers straight wires
MAX_EXPANSIONS = 250_000        # per branch; past it the net falls back to labels
CHAR_W = 5.5                    # label character width, as in desk/draw.py BLOCK_JS (CH)
TEXT_H = 5                      # label text height model (label font size)
WIRED_CLASSES = ("local", "port", "cross")
LABELLED_CLASSES = ("port", "cross")        # wired AND given one interface label
OUT = {0: (1, 0), 180: (-1, 0), 90: (0, 1), 270: (0, -1)}

Cell = Tuple[int, int]


def outward(rot: Any) -> Optional[Tuple[int, int]]:
    """Direction a pin points away from its symbol (desk/draw.py labelPins convention); None if not orthogonal."""
    try:
        r = float(rot or 0)
    except (TypeError, ValueError):
        return None
    if not r.is_integer():
        return None
    return OUT.get(int(r) % 360)


def stub_end(x: float, y: float, rot: Any, s: float) -> Tuple[float, float, int]:
    """End of a labelled stub and the label rotation - identical to desk/draw.py labelPins."""
    r = int(float(rot or 0)) % 360
    if r == 180:
        return x - s, y, 0
    if r == 0:
        return x + s, y, 0
    if r == 270:
        return x, y - (s - 30), 90
    return x, y + (s - 30), 90


def stub_lengths(pins: Sequence[Dict[str, Any]], pin_map: Dict[str, str], stubs: Sequence[float]) -> Dict[str, float]:
    """Stub length per pin number as desk/draw.py labelPins assigns it: pins grouped by rotation, sorted top->bottom
    (left/right pins) or left->right (top/bottom pins), lengths alternating within the group."""
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for p in pins:
        groups.setdefault(str(int(float(p.get("rot") or 0)) % 360), []).append(p)
    out: Dict[str, float] = {}
    for r, arr in groups.items():
        arr = sorted(arr, key=(lambda q: -q["y"]) if r in ("180", "0") else (lambda q: q["x"]))
        for k, p in enumerate(arr):
            if pin_map.get(str(p["num"])) is not None:
                out[str(p["num"])] = stubs[k % 2]
    return out


# ----------------------------------------------------------------------------------------------- planning
class _Grid:
    def __init__(self, window: Sequence[float]):
        x0, y0, x1, y1 = window
        self.xmin, self.ymin = math.ceil(x0 / GRID), math.ceil(y0 / GRID)
        self.xmax, self.ymax = math.floor(x1 / GRID), math.floor(y1 / GRID)
        self.hard: Set[Cell] = set()            # nobody may route here (bodies, tips, label text)
        self.owner: Dict[Cell, str] = {}        # wire / stub cells and reserved escape cells, by net

    def inside(self, c: Cell) -> bool:
        return self.xmin <= c[0] <= self.xmax and self.ymin <= c[1] <= self.ymax


def _cell(x: float, y: float) -> Optional[Cell]:
    if float(x) % GRID or float(y) % GRID:
        return None
    return int(x) // GRID, int(y) // GRID


def _line_cells(a: Cell, b: Cell) -> List[Cell]:
    (ax, ay), (bx, by) = a, b
    if ax == bx:
        st = 1 if by >= ay else -1
        return [(ax, y) for y in range(ay, by + st, st)]
    st = 1 if bx >= ax else -1
    return [(x, ay) for x in range(ax, bx + st, st)]


def _bodies(parts: Dict[str, List[Dict[str, Any]]]) -> Set[Cell]:
    """Cells covered by symbol bodies and pin lines (approximated from the pin tips)."""
    body: Set[Cell] = set()
    for pins in parts.values():
        cells = [(_cell(p["x"], p["y"]), outward(p.get("rot"))) for p in pins]
        cells = [(c, d) for c, d in cells if c is not None and d is not None]
        for c, d in cells:                                   # the pin line itself, pointing inward
            for k in (1, 2):
                body.add((c[0] - k * d[0], c[1] - k * d[1]))
        if len(cells) < 2:
            continue
        xs, ys = [c[0] for c, _ in cells], [c[1] for c, _ in cells]
        L, R, B, T = min(xs), max(xs), min(ys), max(ys)
        if any(d[1] == 0 for _, d in cells):                 # left / right pins: body between them
            for x in range(L + 1, R):
                for y in range(B - 1, T + 2):
                    body.add((x, y))
        if any(d[0] == 0 for _, d in cells):                 # top / bottom pins
            for y in range(B + 1, T):
                for x in range(L - 1, R + 2):
                    body.add((x, y))
    return body


def body_boxes(parts: Dict[str, List[Dict[str, Any]]]) -> Dict[str, List[float]]:
    """Symbol outline model per part, [x0, y0, x1, y1]: the pin tips and pin lines, one grid step wider across the
    pin rows. Used by check_plan for symbol / wire / text overlap (the real outline is not readable over the API)."""
    out: Dict[str, List[float]] = {}
    for ref, pins in sorted(parts.items()):
        pts, horiz, vert = [], False, False
        for p in pins:
            d = outward(p.get("rot"))
            if d is None:
                continue
            x, y = float(p["x"]), float(p["y"])
            pts += [(x, y), (x - 2 * GRID * d[0], y - 2 * GRID * d[1])]
            horiz, vert = horiz or d[1] == 0, vert or d[0] == 0
        if not pts:
            continue
        xs, ys = [q[0] for q in pts], [q[1] for q in pts]
        out[ref] = [min(xs) - (GRID if vert else 0), min(ys) - (GRID if horiz else 0),
                    max(xs) + (GRID if vert else 0), max(ys) + (GRID if horiz else 0)]
    return out


def text_box(label: Dict[str, Any]) -> List[float]:
    """Label text model: from the anchor along the stub direction, len(net) * CHAR_W long, TEXT_H thick."""
    x, y = float(label["at"][0]), float(label["at"][1])
    dx, dy = label.get("dir") or (1, 0)
    n = len(label["net"]) * CHAR_W
    if dx:
        return [min(x, x + dx * n), y, max(x, x + dx * n), y + TEXT_H]
    return [x - TEXT_H, min(y, y + dy * n), x, max(y, y + dy * n)]


def _compress(path: List[Cell]) -> List[Tuple[Cell, Cell]]:
    """A cell path -> maximal straight runs."""
    if len(path) < 2:
        return []
    segs, start = [], path[0]
    for i in range(1, len(path) - 1):
        a, b, c = path[i - 1], path[i], path[i + 1]
        if (b[0] - a[0], b[1] - a[1]) != (c[0] - b[0], c[1] - b[1]):
            segs.append((start, b))
            start = b
    segs.append((start, path[-1]))
    return segs


def _route_branch(g: _Grid, net: str, start: Cell, start_dir: Tuple[int, int], tree: Set[Cell]) -> Optional[List[Cell]]:
    """A* from a pin's escape cell to the nearest cell of `tree`; returns the cell path (start .. join cell)."""
    if start in tree:
        return [start]
    xs, ys = [c[0] for c in tree], [c[1] for c in tree]
    bx0, bx1, by0, by1 = min(xs), max(xs), min(ys), max(ys)

    def h(c: Cell) -> int:
        dx = bx0 - c[0] if c[0] < bx0 else (c[0] - bx1 if c[0] > bx1 else 0)
        dy = by0 - c[1] if c[1] < by0 else (c[1] - by1 if c[1] > by1 else 0)
        return dx + dy

    def free(c: Cell) -> bool:
        if not g.inside(c) or c in g.hard:
            return False
        o = g.owner.get(c)
        return o is None or o == net

    seq = 0
    heap = [(h(start), 0, seq, start, start_dir)]
    best = {(start, start_dir): 0}
    prev: Dict[Tuple[Cell, Tuple[int, int]], Optional[Tuple[Cell, Tuple[int, int]]]] = {(start, start_dir): None}
    expansions = 0
    while heap:
        _, cost, _, c, d = heapq.heappop(heap)
        if best.get((c, d), 1 << 60) < cost:
            continue
        if c in tree:
            path, k = [], (c, d)
            while k is not None:
                path.append(k[0])
                k = prev[k]
            return path[::-1]
        expansions += 1
        if expansions > MAX_EXPANSIONS:
            return None
        for nd in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            if nd == (-d[0], -d[1]):
                continue
            n = (c[0] + nd[0], c[1] + nd[1])
            if not free(n):
                continue
            nc = cost + 1 + (BEND_COST if nd != d else 0)
            if nc < best.get((n, nd), 1 << 60):
                best[(n, nd)] = nc
                prev[(n, nd)] = (c, d)
                seq += 1
                heapq.heappush(heap, (nc + h(n), nc, seq, n, nd))
    return None


def _split_and_merge(segs: List[Tuple[Cell, Cell]], keep: Set[Cell]) -> List[Tuple[Cell, Cell]]:
    """Split segments where another segment of the same net ends on their interior; then merge collinear
    neighbours through degree-2 points that are not pin tips or label anchors (`keep`)."""
    segs = [(a, b) if a <= b else (b, a) for a, b in segs if a != b]
    ends = {p for s in segs for p in s}
    out: Set[Tuple[Cell, Cell]] = set()
    for a, b in segs:
        cuts = [p for p in _line_cells(a, b)[1:-1] if p in ends]
        pts = [a] + cuts + [b]
        out |= {(pts[i], pts[i + 1]) for i in range(len(pts) - 1)}
    res = sorted(out)
    changed = True
    while changed:
        changed = False
        deg: Dict[Cell, List[int]] = {}
        for i, (a, b) in enumerate(res):
            deg.setdefault(a, []).append(i)
            deg.setdefault(b, []).append(i)
        for p, idx in sorted(deg.items()):
            if len(idx) != 2 or p in keep:
                continue
            (a1, b1), (a2, b2) = res[idx[0]], res[idx[1]]
            if (a1[0] == b1[0] == a2[0] == b2[0]) or (a1[1] == b1[1] == a2[1] == b2[1]):
                q1 = a1 if b1 == p else b1
                q2 = a2 if b2 == p else b2
                res = sorted({s for j, s in enumerate(res) if j not in idx} | {(min(q1, q2), max(q1, q2))})
                changed = True
                break
    return res


def plan_block(block: Dict[str, Any], placed: Dict[str, List[Dict[str, Any]]], classes: Dict[str, str],
               window: Sequence[float], stubs: Sequence[float] = (110, 170),
               force_labels: Iterable[str] = ()) -> Dict[str, Any]:
    """Plan the in-block wiring of one placed block.

    block   : the block spec (parts[].ref / pins / nc), parts in spec order
    placed  : {ref: [{num, x, y, rot}]} pin tips read back after placement (every pin of the symbol)
    classes : {net: power|single|local|port|cross} from desk.spec.classify_nets
    window  : (xmin, ymin, xmax, ymax) the wires must stay inside
    force_labels : nets the caller wants drawn as labels (e.g. a client requirement)

    Returns a JSON-serialisable plan: segments, labels, pin tips, per-net mode and the fallback list."""
    forced: Set[str] = set(force_labels)
    fallback: Dict[str, str] = {}
    for _ in range(len(classes) + 2):
        plan, failed = _plan_once(block, placed, classes, window, stubs, forced | set(fallback))
        if not failed:
            plan["fallback"] = dict(sorted(fallback.items()))
            for n, why in fallback.items():
                plan["nets"][n]["fallback"] = why
            for n in forced & set(plan["nets"]):
                plan["nets"][n]["fallback"] = plan["nets"][n]["fallback"] or "forced to labels by the caller"
            return plan
        fallback.update(failed)
    raise RuntimeError("schematic router did not converge")       # unreachable: each round labels >= 1 more net


def _escape(t: Dict[str, Any]) -> Cell:
    return t["cell"][0] + t["dir"][0], t["cell"][1] + t["dir"][1]


def _plan_once(block, placed, classes, window, stubs, labelled_only):
    g = _Grid(window)
    tips: Dict[str, Dict[str, Any]] = {}          # "REF.NUM" -> {at, net, rot, cell, dir, nc}
    net_pins: Dict[str, List[str]] = {}           # net -> pins in spec order
    failed: Dict[str, str] = {}
    stub_len: Dict[str, float] = {}
    for part in block.get("parts", []):
        ref = part["ref"]
        pins = placed.get(ref, [])
        pmap = {str(k): v for k, v in part.get("pins", {}).items()}
        ncs = {str(n) for n in part.get("nc", [])}
        for k, v in stub_lengths(pins, pmap, stubs).items():
            stub_len[f"{ref}.{k}"] = v
        for p in pins:
            tips[f"{ref}.{p['num']}"] = {"at": [p["x"], p["y"]], "net": pmap.get(str(p["num"])), "rot": p.get("rot"),
                                         "cell": _cell(p["x"], p["y"]), "dir": outward(p.get("rot")),
                                         "nc": str(p["num"]) in ncs}
        for num, net in part.get("pins", {}).items():
            net_pins.setdefault(net, []).append(f"{ref}.{num}")

    mode: Dict[str, str] = {}
    for net, pids in net_pins.items():
        wired = classes.get(net, "single") in WIRED_CLASSES and net not in labelled_only and len(pids) >= 2
        if wired:
            bad = [p for p in pids if p not in tips or tips[p]["cell"] is None or tips[p]["dir"] is None]
            if bad:
                failed[net] = f"pin {bad[0]} is missing, off the {GRID}-unit grid or not orthogonal"
        mode[net] = "wire" if wired else "label"
    if failed:
        return None, failed

    g.hard |= _bodies(placed)
    for t in tips.values():                       # every tip is untouchable except as its own wire's end point
        if t["cell"] is not None:
            g.hard.add(t["cell"])

    segments: List[Dict[str, Any]] = []
    labels: List[Dict[str, Any]] = []
    raw: Dict[str, List[Tuple[Cell, Cell]]] = {}
    tree: Dict[str, Set[Cell]] = {}
    keep: Dict[str, Set[Cell]] = {}

    def add_stub(net: str, pid: str, joinable: bool) -> None:
        t = tips[pid]
        x, y = t["at"]
        ex_, ey, lrot = stub_end(x, y, t["rot"], stub_len.get(pid, stubs[0]))
        labels.append({"net": net, "at": [ex_, ey], "rotation": lrot, "pin": pid, "dir": list(t["dir"] or (1, 0))})
        a, b = t["cell"], _cell(ex_, ey)
        if a is None or b is None or t["dir"] is None:     # off-grid pin: drawn exactly like the labels style
            segments.append({"net": net, "a": [x, y], "b": [ex_, ey]})
            return
        raw.setdefault(net, []).append((a, b))
        keep.setdefault(net, set()).update({a, b})
        for c in _line_cells(a, b)[1:]:
            if g.owner.get(c, net) != net or c in g.hard:
                failed.setdefault(net, f"stub of {pid} runs into another net or a part")
            g.owner[c] = net
        if joinable:
            tree.setdefault(net, set()).update(_line_cells(a, b)[1:])
        d = t["dir"]
        for k in range(1, math.ceil(len(net) * CHAR_W / GRID) + 2):   # the label text runs on along the stub
            g.hard.add((b[0] + k * d[0], b[1] + k * d[1]))

    # 1. labels first (power rails, single pins, fallbacks): their stubs and text are reserved before any wire
    for net, pids in net_pins.items():
        if mode[net] == "label":
            for pid in pids:
                if pid in tips:
                    add_stub(net, pid, joinable=False)
    failed.clear()          # a labels-style stub collision is drawn exactly as the labels style would; check_plan reports it
    # 2. reserve the escape cell of every wired pin for its own net, and keep NC pins' escape cells empty
    for pid, t in tips.items():
        if t["cell"] is None or t["dir"] is None:
            continue
        esc = _escape(t)
        if t["net"] is not None and mode.get(t["net"]) == "wire":
            if g.owner.get(esc, t["net"]) != t["net"] or esc in g.hard:
                failed[t["net"]] = f"escape of {pid} is blocked"
            g.owner.setdefault(esc, t["net"])
        elif t["nc"]:
            g.hard.add(esc)
    # 3. interface label of port / cross nets: one labelled stub on the first pin seeds the tree
    for net, pids in net_pins.items():
        if mode[net] == "wire" and classes.get(net) in LABELLED_CLASSES and net not in failed:
            add_stub(net, pids[0], joinable=True)
    if failed:
        return None, failed

    def span(net):
        xs = [tips[p]["at"][0] for p in net_pins[net]]
        ys = [tips[p]["at"][1] for p in net_pins[net]]
        return max(xs) - min(xs) + max(ys) - min(ys), net

    # 4. route the wired nets, shortest first; each pin joins the tree at its nearest point
    for net in sorted((n for n in net_pins if mode[n] == "wire"), key=span):
        pids = list(net_pins[net])
        tr = tree.setdefault(net, set())
        segs = raw.setdefault(net, [])
        kp = keep.setdefault(net, set())
        if not tr:                                # local net: the first pin's escape seeds the tree
            t = tips[pids[0]]
            segs.append((t["cell"], _escape(t)))
            kp.add(t["cell"])
            tr.add(_escape(t))
        todo = pids[1:]
        while todo:
            pid = min(todo, key=lambda p: (min(abs(_escape(tips[p])[0] - c[0]) + abs(_escape(tips[p])[1] - c[1])
                                               for c in tr), todo.index(p)))
            todo.remove(pid)
            t = tips[pid]
            path = _route_branch(g, net, _escape(t), t["dir"], tr)
            if path is None:
                failed[net] = f"no free path for {pid} inside the block window"
                break
            segs.append((t["cell"], _escape(t)))
            kp.add(t["cell"])
            segs += _compress(path)
            for c in path:
                g.owner[c] = net
            tr.update(path)
    if failed:
        return None, failed

    for net in sorted(raw):
        for a, b in _split_and_merge(raw[net], keep.get(net, set())):
            segments.append({"net": net, "a": [a[0] * GRID, a[1] * GRID], "b": [b[0] * GRID, b[1] * GRID]})
    segments.sort(key=lambda s: (s["net"], s["a"], s["b"]))
    labels.sort(key=lambda l: (l["net"], l["at"]))
    nets = {n: {"class": classes.get(n, "single"), "mode": mode[n], "pins": net_pins[n], "fallback": None}
            for n in sorted(net_pins)}
    pins = {pid: {"at": t["at"], "net": t["net"], "nc": t["nc"]} for pid, t in sorted(tips.items())}
    return {"block": block.get("id"), "policy": "subsystem", "grid": GRID, "window": list(window),
            "nets": nets, "segments": segments, "labels": labels, "pins": pins,
            "junctions": junctions_of(segments), "bodies": body_boxes(placed)}, {}


def junctions_of(segments: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Junction dots: every point where three or more wire ends of the same net meet (T or cross junction)."""
    deg: Dict[Tuple[str, Tuple[float, float]], int] = {}
    for s in segments:
        for p in (s["a"], s["b"]):
            k = (s["net"], (p[0], p[1]))
            deg[k] = deg.get(k, 0) + 1
    return [{"net": n, "at": [p[0], p[1]]} for (n, p), d in sorted(deg.items()) if d >= 3]


def plan_labels(block: Dict[str, Any], placed: Dict[str, List[Dict[str, Any]]],
                stubs: Sequence[float] = (110, 170)) -> Dict[str, Any]:
    """The geometry the `labels` style draws (a stub + label on every connected pin), as a plan the checker can
    read. Used to prove both styles give the same netlist; the live `labels` drawing stays desk/draw.py BLOCK_JS."""
    segments, labels, pins = [], [], {}
    for part in block.get("parts", []):
        ref, pmap = part["ref"], {str(k): v for k, v in part.get("pins", {}).items()}
        ncs = {str(n) for n in part.get("nc", [])}
        ps = placed.get(ref, [])
        lens = stub_lengths(ps, pmap, stubs)
        for p in ps:
            pid, net = f"{ref}.{p['num']}", pmap.get(str(p["num"]))
            pins[pid] = {"at": [p["x"], p["y"]], "net": net, "nc": str(p["num"]) in ncs}
            if net is None:
                continue
            ex_, ey, lrot = stub_end(p["x"], p["y"], p.get("rot"), lens[str(p["num"])])
            segments.append({"net": net, "a": [p["x"], p["y"]], "b": [ex_, ey]})
            labels.append({"net": net, "at": [ex_, ey], "rotation": lrot, "pin": pid,
                           "dir": list(outward(p.get("rot")) or (1, 0))})
    return {"block": block.get("id"), "policy": "labels", "segments": segments, "labels": labels, "pins": pins,
            "nets": {}, "fallback": {}, "bodies": body_boxes(placed)}


# ----------------------------------------------------------------------------------------------- checking
def _seg_points(s: Dict[str, Any]) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    return (float(s["a"][0]), float(s["a"][1])), (float(s["b"][0]), float(s["b"][1]))


def _on_segment(p, a, b) -> bool:
    return (min(a[0], b[0]) <= p[0] <= max(a[0], b[0]) and min(a[1], b[1]) <= p[1] <= max(a[1], b[1])
            and (a[0] == b[0] == p[0] or a[1] == b[1] == p[1]))


def _intersection(s1, s2):
    """Intersection of two axis-aligned segments: None, ('point', p) or ('overlap', None)."""
    (a, b), (c, d) = s1, s2
    if a == b or c == d:                    # degenerate: a point
        p = a if a == b else c
        q1, q2 = (c, d) if a == b else (a, b)
        return ("point", p) if _on_segment(p, q1, q2) else None
    h1, h2 = a[1] == b[1], c[1] == d[1]
    if h1 == h2:                            # parallel
        if (h1 and a[1] != c[1]) or (not h1 and a[0] != c[0]):
            return None
        k = 0 if h1 else 1
        lo = max(min(a[k], b[k]), min(c[k], d[k]))
        hi = min(max(a[k], b[k]), max(c[k], d[k]))
        if lo > hi:
            return None
        if lo == hi:
            return "point", ((lo, a[1]) if h1 else (a[0], lo))
        return "overlap", None
    hs, vs = (s1, s2) if h1 else (s2, s1)
    p = (vs[0][0], hs[0][1])
    return ("point", p) if _on_segment(p, *hs) and _on_segment(p, *vs) else None


def _open_overlap(r1, r2) -> bool:
    return max(r1[0], r2[0]) < min(r1[2], r2[2]) and max(r1[1], r2[1]) < min(r1[3], r2[3])


def _seg_in_box(a, b, r) -> bool:
    if a[1] == b[1]:
        return r[1] < a[1] < r[3] and max(min(a[0], b[0]), r[0]) < min(max(a[0], b[0]), r[2])
    return r[0] < a[0] < r[2] and max(min(a[1], b[1]), r[1]) < min(max(a[1], b[1]), r[3])


def overlap_errors(plan: Dict[str, Any]) -> List[str]:
    """Readability checks on the symbol and text models: symbols overlapping symbols, a wire hidden under a symbol
    or a label, label text over a symbol or over other label text."""
    E: List[str] = []
    bodies = sorted((plan.get("bodies") or {}).items())
    boxes = [(lab, text_box(lab)) for lab in plan.get("labels", [])]
    for i in range(len(bodies)):
        for j in range(i + 1, len(bodies)):
            if _open_overlap(bodies[i][1], bodies[j][1]):
                E.append(f"overlap: symbols {bodies[i][0]} and {bodies[j][0]} overlap")
    for s in plan.get("segments", []):
        a, b = _seg_points(s)
        for ref, r in bodies:
            if _seg_in_box(a, b, r):
                E.append(f"overlap: {s['net']} wire {a}-{b} runs under symbol {ref}")
        for lab, r in boxes:
            if _seg_in_box(a, b, r):
                E.append(f"overlap: {s['net']} wire {a}-{b} runs under label {lab['net']} at {lab['at']}")
    for k, (lab, r) in enumerate(boxes):
        for ref, rb in bodies:
            if _open_overlap(r, rb):
                E.append(f"overlap: label {lab['net']} at {lab['at']} covers symbol {ref}")
        for lab2, r2 in boxes[k + 1:]:
            if _open_overlap(r, r2):
                E.append(f"overlap: labels {lab['net']} at {lab['at']} and {lab2['net']} at {lab2['at']} overlap")
    return E


def spec_netlist(block: Dict[str, Any]) -> Dict[str, List[str]]:
    nets: Dict[str, List[str]] = {}
    for p in block.get("parts", []):
        for num, net in p.get("pins", {}).items():
            nets.setdefault(net, []).append(f"{p['ref']}.{num}")
    return {n: sorted(v) for n, v in sorted(nets.items())}


def check_plan(plan: Dict[str, Any], block: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Independent geometric + electrical check of a drawing plan (either style).

    Errors: crossing / touching wires of different nets, overlapping wires, a junction in the middle of a wire,
    a wire running over a pin, a wire or label on a pin of another net, a floating label, a spec net split into
    several pieces (open) or two nets merged (short). With `block`, the derived netlist must equal the spec's."""
    segs = [(_seg_points(s), s["net"]) for s in plan.get("segments", [])]
    E: List[str] = []
    crossings = 0
    for i in range(len(segs)):
        for j in range(i + 1, len(segs)):
            (s1, n1), (s2, n2) = segs[i], segs[j]
            x = _intersection(s1, s2)
            if x is None:
                continue
            if n1 != n2:
                crossings += 1
                E.append(f"short: {n1} wire {s1} meets {n2} wire {s2}")
            elif x[0] == "overlap":
                E.append(f"overlap: two {n1} wires share {s1} / {s2}")
            elif x[1] not in s1 or x[1] not in s2:
                E.append(f"{n1}: wires cross or T-join mid-segment at {x[1]} (junctions must be shared end points)")
    ends: Dict[Tuple[str, Tuple[float, float]], int] = {}
    for s, n in segs:
        for q in s:
            ends[(n, q)] = ends.get((n, q), 0) + 1
    anchors = {(p.get("net"), (float(p["at"][0]), float(p["at"][1]))) for p in plan.get("pins", {}).values()}
    anchors |= {(l["net"], (float(l["at"][0]), float(l["at"][1]))) for l in plan.get("labels", [])}
    for (n, q), d in sorted(ends.items()):
        if d == 1 and (n, q) not in anchors:
            E.append(f"{n}: dangling wire end at {q} (not on a pin, label or another wire of the net)")
    for pid, p in sorted(plan.get("pins", {}).items()):
        pt = (float(p["at"][0]), float(p["at"][1]))
        for s, n in segs:
            if _on_segment(pt, *s):
                if n != p.get("net"):
                    E.append(f"short: {n} wire touches pin {pid} ({p.get('net') or 'NC/unconnected'})")
                elif pt not in s:
                    E.append(f"{n}: wire runs over pin {pid} instead of ending on it")
    for lab in plan.get("labels", []):
        pt = (float(lab["at"][0]), float(lab["at"][1]))
        on = [(s, n) for s, n in segs if _on_segment(pt, *s)]
        if any(n != lab["net"] for _, n in on):
            E.append(f"short: label {lab['net']} at {pt} sits on a wire of another net")
        if not any(n == lab["net"] and pt in s for s, n in on):
            E.append(f"floating label {lab['net']} at {pt} (not on the end of one of its wires)")
    E += overlap_errors(plan)
    if "junctions" in plan:
        want_dots = {(j["net"], tuple(map(float, j["at"]))) for j in junctions_of(plan.get("segments", []))}
        have_dots = {(j["net"], tuple(map(float, j["at"]))) for j in plan["junctions"]}
        for n, p in sorted(want_dots - have_dots):
            E.append(f"{n}: junction at {p} has no junction dot")
        for n, p in sorted(have_dots - want_dots):
            E.append(f"{n}: junction dot at {p} where fewer than three wires meet")
    derived, conn_errors = derive_netlist(plan)
    E += conn_errors
    if block is not None:
        want = spec_netlist(block)
        for net in sorted(set(want) | set(derived)):
            if want.get(net, []) != derived.get(net, []):
                E.append(f"netlist: {net} drawn {derived.get(net, [])} != spec {want.get(net, [])}")
    return {"ok": not E, "errors": E, "crossings": crossings, "segments": len(segs),
            "labels": len(plan.get("labels", [])), "netlist": derived}


def derive_netlist(plan: Dict[str, Any]) -> Tuple[Dict[str, List[str]], List[str]]:
    """The netlist a drawing implies: wires connect at shared end points, a pin joins the wire that ends on its tip,
    labels with the same name join (net labels are global, as in EasyEDA). Returns ({net: [REF.PIN]}, errors)."""
    parent: Dict[Any, Any] = {}

    def find(a):
        parent.setdefault(a, a)
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    names: Dict[Any, Set[str]] = {}
    for s in plan.get("segments", []):
        a, b = _seg_points(s)
        union(("pt", a), ("pt", b))
        names.setdefault(("pt", a), set()).add(s["net"])
    for lab in plan.get("labels", []):
        pt = ("pt", (float(lab["at"][0]), float(lab["at"][1])))
        union(pt, ("label", lab["net"]))
        names.setdefault(pt, set()).add(lab["net"])
    for pid, p in plan.get("pins", {}).items():
        pt = ("pt", (float(p["at"][0]), float(p["at"][1])))
        if pt in parent:
            union(pt, ("pin", pid))
    comp_names: Dict[Any, Set[str]] = {}
    for node, ns in names.items():
        comp_names.setdefault(find(node), set()).update(ns)
    E: List[str] = []
    out: Dict[str, List[str]] = {}
    pieces: Dict[str, Set[Any]] = {}
    for pid, p in sorted(plan.get("pins", {}).items()):
        if ("pin", pid) not in parent:
            if p.get("net"):
                E.append(f"open: pin {pid} ({p['net']}) has no wire or label")
            continue
        root = find(("pin", pid))
        ns = comp_names.get(root, set())
        out.setdefault(sorted(ns)[0] if ns else "?", []).append(pid)
        if p.get("net"):
            pieces.setdefault(p["net"], set()).add(root)
    for root, ns in sorted(comp_names.items(), key=lambda kv: sorted(kv[1])):
        if len(ns) > 1:
            E.append(f"short: nets {sorted(ns)} are joined")
    for net, roots in sorted(pieces.items()):
        if len(roots) > 1:
            E.append(f"open: net {net} is drawn as {len(roots)} separate pieces")
    return {n: sorted(v) for n, v in sorted(out.items())}, E


def check_saved_plans(project: str, blocks: Sequence[Dict[str, Any]], ids: Iterable[str],
                      layout: Dict[str, Any], project_json: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    """tools/verify.py: a block BUILT with `subsystem` wiring (state/layout.json says so) must have a saved plan
    that passes check_plan against its CURRENT spec. Blocks built with `labels` are only reported when the policy
    now says `subsystem` (migrated project: rebuild to migrate them; never done silently). Returns (errors, notes)."""
    import json
    import os
    from desk import spec as S
    E: List[str] = []
    notes: List[str] = []
    ids = set(ids)
    for b in blocks:
        if b.get("id") not in ids:
            continue
        bid = b["id"]
        built_with = (layout.get(bid) or {}).get("wiring", "labels")
        try:
            policy = S.wiring_policy(project_json, b)
        except ValueError as e:
            E.append(f"{bid}: {e}")
            continue
        if built_with != "subsystem":
            if policy == "subsystem" and bid in layout:
                notes.append(f"{bid}: drawn with labels, policy is now subsystem - clear_block + build to migrate it")
            continue
        f = os.path.join(project, "state", "wiring", bid + ".json")
        if not os.path.exists(f):
            E.append(f"{bid}: built with subsystem wiring but state/wiring/{bid}.json is missing - nothing to check")
            continue
        with open(f, encoding="utf-8") as h:
            plan = json.load(h)
        res = check_plan(plan, b)
        E += [f"{bid} wiring: {e}" for e in res["errors"]]
        if res["ok"]:
            notes.append(f"{bid}: subsystem wiring plan OK - {res['segments']} wires, {res['crossings']} crossings, "
                         f"{len(plan.get('fallback', {}))} nets fell back to labels")
    return E, notes
