"""Deterministic placement rules (docs/04_PLACEMENT.md). Pure functions -> unit-testable without EasyEDA.

Input  dump : state/pcb_dump.json from tools/pcb_dump.py  {ref: {x,y (mil, PCB frame), rot, layer (1 top/2 bottom),
              fp, bbox:[minX,maxX,minY,maxY] rel. mil, pads:[{num,dx,dy,shape:[kind,w,h,..] mil,rot,net,layer}]}}
       plan : projects/<P>/placement.json (mm, board-local; see templates/placement.template.json)
Output (errors, warnings, metrics). Every number used comes from plan["rules"] (defaults in RULES)."""
import math, re, collections

MIL = 39.37007874
RULES = {
    "edge_pad_mm": 0.30, "edge_body_mm": 0.0, "connector_edge_mm": 1.0, "connector_front_keepout_mm": 3.0,
    "connector_clearance_mm": 1.0, "esd_max_mm": 3.0, "sensor_heat_mm": 7.0, "heat_spacing_mm": 3.0,
    "rf_edge_mm": 0.5, "decap_max_mm": 2.0, "max_utilisation": 0.55, "density_cell_mm": 2.5, "hotspot_fill": 0.85,
    "unbalanced_free_fraction": 0.15, "hotspot_neighbours": 4, "tall_mm": 3.0,
    # pad-to-pad / body-to-body by class (mm); pair value = rule in pair_clearance()
    "pad": {"p0201": 0.20, "p0402": 0.25, "p0603": 0.30, "ic": 0.40, "fine": 0.50, "connector": 0.50, "tall": 0.50},
    "body": {"p0201": 0.15, "p0402": 0.20, "p0603": 0.25, "ic": 0.30, "fine": 0.50, "connector": 1.00, "tall": 1.00},
    "passive_ic_pad": 0.30, "passive_ic_body": 0.25,
}
CONN_RX = re.compile(r"^(J|P|CN|USB|H|FPC|CON|X)\d", re.I)
PASSIVE_RX = re.compile(r"^(R|C|L|FB|D|LED|F)\d", re.I)
GND_RX = re.compile(r"GND|VSS", re.I)


class Part:
    __slots__ = ("ref", "side", "body", "pads", "cls", "rot", "fp", "npads")

    def __init__(self, ref, c, ox, oy):
        x, y = c["x"] / MIL - ox, c["y"] / MIL - oy
        b = c.get("bbox") or [0, 0, 0, 0]
        self.ref, self.side, self.rot, self.fp = ref, ("T" if c.get("layer", 1) == 1 else "B"), c.get("rot", 0) or 0, c.get("fp") or ""
        self.body = (x + b[0] / MIL, x + b[1] / MIL, y + b[2] / MIL, y + b[3] / MIL)
        self.pads = []
        for p in c.get("pads", []):
            sz = p.get("shape")
            w, h = (sz[1] / MIL / 2, sz[2] / MIL / 2) if isinstance(sz, list) and len(sz) > 2 and isinstance(sz[1], (int, float)) else (0.2, 0.2)
            a = math.radians(p.get("rot") or 0); W = abs(w * math.cos(a)) + abs(h * math.sin(a)); H = abs(w * math.sin(a)) + abs(h * math.cos(a))
            px, py = x + p["dx"] / MIL, y + p["dy"] / MIL
            tht = p.get("layer") in (11, 12)       # multi-layer pad
            self.pads.append((px - W, px + W, py - H, py + H, p.get("net") or "", "TB" if tht else self.side, p.get("num")))
        self.npads = len(self.pads)
        self.cls = None

    def center(self):
        return ((self.body[0] + self.body[1]) / 2, (self.body[2] + self.body[3]) / 2)


def classify(p, roles, heights, R):
    if p.ref in roles.get("connectors", []) or (CONN_RX.match(p.ref) and p.ref not in roles.get("not_connectors", [])): return "connector"
    if heights.get(p.ref, 0) > R["tall_mm"]: return "tall"
    f = p.fp.upper()
    if PASSIVE_RX.match(p.ref) and p.npads <= 3:
        for k, cls in (("0201", "p0201"), ("0402", "p0402"), ("0603", "p0603"), ("0805", "p0603"), ("1206", "p0603")):
            if k in f: return cls
        return "p0402"
    if "BGA" in f or _min_pitch(p) <= 0.5: return "fine"
    return "ic"


def _min_pitch(p):
    if p.npads < 8: return 9
    cs = sorted(((a[0] + a[1]) / 2, (a[2] + a[3]) / 2) for a in p.pads)
    best = 9
    for i in range(len(cs) - 1):
        for j in range(i + 1, min(i + 6, len(cs))):
            best = min(best, math.hypot(cs[i][0] - cs[j][0], cs[i][1] - cs[j][1]))
    return best


def pair_clearance(a, b, R, kind):
    ca, cb = a.cls, b.cls
    pas = {"p0201", "p0402", "p0603"}
    if (ca in pas and cb == "ic") or (cb in pas and ca == "ic"):
        return R["passive_ic_pad" if kind == "pad" else "passive_ic_body"]
    return max(R[kind][ca], R[kind][cb])


def _gap(r1, r2):
    """Distance between two axis-aligned rectangles (negative = overlap depth)."""
    dx = max(r2[0] - r1[1], r1[0] - r2[1]); dy = max(r2[2] - r1[3], r1[2] - r2[3])
    if dx < 0 and dy < 0: return max(dx, dy)
    return math.hypot(max(dx, 0), max(dy, 0))


def _edge_dist(r, W, H):
    return min(r[0], r[2], W - r[1], H - r[3])


def _inside(r, z):
    return not (r[1] <= z[0] or r[0] >= z[2] or r[3] <= z[1] or r[2] >= z[3])


def check(dump, plan, blocks=(), profile=None):
    R = dict(RULES); R.update({k: v for k, v in plan.get("rules", {}).items() if k not in ("pad", "body")})
    if profile:
        if hasattr(profile, "manufacturing"):
            mfg = profile.manufacturing
            R["edge_pad_mm"] = mfg.copper_to_edge_mil / 39.37007874
            min_c_mm = mfg.min_clearance_mil / 39.37007874
            for k in R["pad"]:
                R["pad"][k] = max(R["pad"][k], min_c_mm)
        if hasattr(profile, "thermal"):
            if profile.thermal.max_temperature_rise_c < 10.0:
                R["heat_spacing_mm"] = max(R["heat_spacing_mm"], 5.0)
    for k in ("pad", "body"): R[k] = {**RULES[k], **plan.get("rules", {}).get(k, {})}
    ox, oy = plan.get("origin_mm", [0, 0]); W, H = plan["board_mm"]
    roles, heights = plan.get("roles", {}), plan.get("heights", {})
    P = {r: Part(r, c, ox, oy) for r, c in dump.items() if r}
    for p in P.values(): p.cls = classify(p, roles, heights, R)
    E, Wn, M = [], [], {}

    # ---- board containment + edge clearance
    over = set(plan.get("overhang_allowed", []))
    for p in P.values():
        if p.ref not in over and _edge_dist(p.body, W, H) < R["edge_body_mm"] - 1e-6:
            E.append(f"{p.ref}: body outside board / within {R['edge_body_mm']} mm of edge ({_edge_dist(p.body, W, H):.2f} mm)")
        for pad in p.pads:
            if p.ref not in over and _edge_dist(pad, W, H) < R["edge_pad_mm"] - 1e-6:
                E.append(f"{p.ref}.{pad[6]}: pad {_edge_dist(pad, W, H):.2f} mm from board edge < {R['edge_pad_mm']}"); break
        if p.rot % 90: Wn.append(f"{p.ref}: non-orthogonal rotation {p.rot}°")

    # ---- pad-to-pad and body-to-body between different parts (spatial hash)
    cell = 3.0; grid = collections.defaultdict(list)
    for p in P.values():
        for i in range(int(p.body[0] // cell) - 1, int(p.body[1] // cell) + 2):
            for j in range(int(p.body[2] // cell) - 1, int(p.body[3] // cell) + 2):
                grid[(i, j)].append(p.ref)
    pairs = set()
    for refs in grid.values():
        for i in range(len(refs)):
            for j in range(i + 1, len(refs)): pairs.add(tuple(sorted((refs[i], refs[j]))))
    worst = collections.defaultdict(lambda: 9.0)
    for ra, rb in pairs:
        a, b = P[ra], P[rb]
        body_gap = _gap(a.body, b.body)
        if a.side == b.side:
            need = pair_clearance(a, b, R, "body")
            if body_gap < 0: E.append(f"{ra} <-> {rb}: bodies overlap ({-body_gap:.2f} mm)")
            elif body_gap < need: Wn.append(f"{ra} <-> {rb}: body gap {body_gap:.2f} mm < {need} ({a.cls}/{b.cls})")
        need = pair_clearance(a, b, R, "pad")
        # If components are physically far apart, their pads cannot violate clearance
        if body_gap > need + 1.5:
            continue
        for pa in a.pads:
            sa = pa[5]
            for pb in b.pads:
                sb = pb[5]
                if sa != sb and sa != "TB" and sb != "TB": continue
                g = _gap(pa, pb)
                if g < worst[(ra, rb)]: worst[(ra, rb)] = g
        if worst[(ra, rb)] < need - 1e-6:
            E.append(f"{ra} <-> {rb}: pad-to-pad {worst[(ra, rb)]:.2f} mm < {need} ({a.cls}/{b.cls})")

    # ---- connectors: at edge, front keep-out, clearance, ESD close behind
    conns = [p for p in P.values() if p.cls == "connector"]
    for c in conns:
        d = _edge_dist(c.body, W, H)
        if d > R["connector_edge_mm"]: E.append(f"{c.ref}: connector {d:.2f} mm from board edge > {R['connector_edge_mm']}")
        b = c.body; sides = {"L": b[0], "B": b[2], "R": W - b[1], "T": H - b[3]}; s = min(sides, key=sides.get)
        k = R["connector_front_keepout_mm"]
        front = {"L": (0, b[2], b[0], b[3]), "R": (b[1], b[2], W, b[3]), "B": (b[0], 0, b[1], b[2]), "T": (b[0], b[3], b[1], H)}[s]
        # strip between connector body and its edge (cable/plug side), plus k mm into the board if the body is set back
        front = {"L": (0, front[1], max(front[2], min(k, b[0])), front[3]), "R": (min(front[0], max(W - k, b[1])), front[1], W, front[3]),
                 "B": (front[0], 0, front[2], max(front[3], min(k, b[2]))), "T": (front[0], min(front[1], max(H - k, b[3])), front[2], H)}[s] if d > 0 else front
        for p in P.values():
            if p is c or p.side != c.side: continue
            if _inside(p.body, front): E.append(f"{p.ref}: inside the mating/front keep-out of connector {c.ref}")
            elif p.cls != "connector" and _gap(p.body, c.body) < R["connector_clearance_mm"] and p.cls.startswith("p0"):
                Wn.append(f"{p.ref}: {_gap(p.body, c.body):.2f} mm from connector {c.ref} body (< {R['connector_clearance_mm']}; MLCC crack / rework)")
        sig_nets = {pad[4] for pad in c.pads if pad[4] and not GND_RX.search(pad[4])}
        for net in sorted(sig_nets):
            prot = [P[r] for r in roles.get("esd", []) if r in P and any(pd[4] == net for pd in P[r].pads)]
            for p in prot:
                g = _gap(p.body, c.body)
                if g > R["esd_max_mm"]: Wn.append(f"{p.ref}: ESD for {c.ref}/{net} is {g:.1f} mm away (> {R['esd_max_mm']})")

    # ---- sensors vs heat, heat spreading, RF at edge
    heat = [P[r] for r in roles.get("heat", []) if r in P] + [p for p in P.values() if re.match(r"^L\d", p.ref) and p.ref not in roles.get("heat", []) and roles.get("inductors_are_heat", True)]
    for s in [P[r] for r in roles.get("sensors", []) if r in P]:
        for h in heat:
            g = _gap(s.body, h.body)
            if g < R["sensor_heat_mm"]: E.append(f"{s.ref}: sensor {g:.1f} mm from heat source {h.ref} (< {R['sensor_heat_mm']})")
    hs = [P[r] for r in roles.get("heat", []) if r in P]
    for i in range(len(hs)):
        for j in range(i + 1, len(hs)):
            g = _gap(hs[i].body, hs[j].body)
            if g < R["heat_spacing_mm"]: Wn.append(f"{hs[i].ref} <-> {hs[j].ref}: heat sources {g:.1f} mm apart (< {R['heat_spacing_mm']})")
    for r in roles.get("rf", []):
        if r in P and _edge_dist(P[r].body, W, H) > R["rf_edge_mm"]:
            E.append(f"{r}: RF/antenna part {_edge_dist(P[r].body, W, H):.1f} mm from board edge (> {R['rf_edge_mm']})")

    # ---- keep-outs, reserved areas, height zones
    for z in plan.get("keepouts", []):
        rect, side, allow = z["rect_mm"], z.get("side", "both"), set(z.get("allow", []))
        for p in P.values():
            if p.ref in allow or (side != "both" and p.side != side): continue
            if _inside(p.body, rect): E.append(f"{p.ref}: inside keep-out '{z.get('name', '?')}'")
    for z in plan.get("height_zones", []):
        for p in P.values():
            hgt = heights.get(p.ref)
            if hgt is not None and (z.get("side", "both") in ("both", p.side)) and _inside(p.body, z["rect_mm"]) and hgt > z["max_mm"]:
                E.append(f"{p.ref}: {hgt} mm tall in height zone '{z.get('name', '?')}' (max {z['max_mm']})")

    # ---- decoupling distance + same side (from block spec roles "Uxx ... at pin N")
    for b in blocks:
        for sp in b.get("parts", []):
            m = re.search(r"\b((?:U|IC)\d+)\b.*?\bpin (\w+)", sp.get("role", ""))
            if not m or sp["ref"] not in P or m.group(1) not in P: continue
            ic, cap = P[m.group(1)], P[sp["ref"]]
            pad = next((q for q in ic.pads if str(q[6]) == m.group(2)), None)
            if not pad: continue
            d = _gap(cap.body, pad)
            if d > R["decap_max_mm"]: E.append(f"{cap.ref}: {d:.1f} mm from {ic.ref} pin {m.group(2)} (> {R['decap_max_mm']})")
            if cap.side != ic.side: Wn.append(f"{cap.ref}: on {cap.side}, its IC {ic.ref} on {ic.side}")

    # ---- density, hotspots, free space per side
    cs = R["density_cell_mm"]; nx, ny = max(1, int(math.ceil(W / cs))), max(1, int(math.ceil(H / cs)))
    excl = [z["rect_mm"] for z in plan.get("keepouts", []) + plan.get("reserved", [])]
    for side in ("T", "B"):
        fill = [[0.0] * ny for _ in range(nx)]; usable = [[True] * ny for _ in range(nx)]
        for i in range(nx):
            for j in range(ny):
                c = (i * cs, j * cs, min(W, (i + 1) * cs), min(H, (j + 1) * cs))
                usable[i][j] = not any(_inside((c[0], c[2], c[1], c[3]), z) and (c[2] - c[0]) > 0 for z in excl)
        area = 0.0
        for p in P.values():
            if p.side != side: continue
            bx = (max(0, p.body[0]), min(W, p.body[1]), max(0, p.body[2]), min(H, p.body[3]))
            if bx[1] <= bx[0] or bx[3] <= bx[2]: continue
            area += (bx[1] - bx[0]) * (bx[3] - bx[2])
            for i in range(int(bx[0] // cs), min(nx, int(bx[1] // cs) + 1)):
                for j in range(int(bx[2] // cs), min(ny, int(bx[3] // cs) + 1)):
                    ov = max(0, min(bx[1], (i + 1) * cs) - max(bx[0], i * cs)) * max(0, min(bx[3], (j + 1) * cs) - max(bx[2], j * cs))
                    fill[i][j] = min(1.0, fill[i][j] + ov / (cs * cs))
        n_us = sum(usable[i][j] for i in range(nx) for j in range(ny)) or 1
        util = area / (n_us * cs * cs)
        hot = [(i, j) for i in range(nx) for j in range(ny) if usable[i][j] and fill[i][j] >= R["hotspot_fill"] and
               sum(1 for di in (-1, 0, 1) for dj in (-1, 0, 1) if (di or dj) and 0 <= i + di < nx and 0 <= j + dj < ny
                   and fill[i + di][j + dj] >= R["hotspot_fill"]) >= R["hotspot_neighbours"]]
        # largest empty connected region (4-neighbour) of usable cells with < 5 % fill
        seen, best = set(), (0, None)
        for i in range(nx):
            for j in range(ny):
                if (i, j) in seen or not usable[i][j] or fill[i][j] >= 0.05: continue
                stack, comp = [(i, j)], []
                seen.add((i, j))
                while stack:
                    a, b2 = stack.pop(); comp.append((a, b2))
                    for da, db in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        q = (a + da, b2 + db)
                        if 0 <= q[0] < nx and 0 <= q[1] < ny and q not in seen and usable[q[0]][q[1]] and fill[q[0]][q[1]] < 0.05:
                            seen.add(q); stack.append(q)
                if len(comp) > best[0]: best = (len(comp), comp)
        free = best[0] * cs * cs
        bbox = None
        if best[1]:
            xs = [c[0] for c in best[1]]; ys = [c[1] for c in best[1]]
            bbox = [round(min(xs) * cs, 1), round(min(ys) * cs, 1), round((max(xs) + 1) * cs, 1), round((max(ys) + 1) * cs, 1)]
        pins = sum(len(p.pads) for p in P.values() if p.side == side)
        M[side] = {"parts": sum(1 for p in P.values() if p.side == side), "utilisation": round(util, 3), "hotspot_cells": len(hot),
                   "largest_free_mm2": round(free, 1), "largest_free_rect_mm": bbox, "pins_per_cm2": round(pins / (W * H / 100), 1)}
        if M[side]["parts"] == 0: continue
        if util > R["max_utilisation"]:
            E.append(f"side {side}: utilisation {util:.0%} > {R['max_utilisation']:.0%} (over-populated: move parts to the other side, "
                     f"use smaller packages, or enlarge the board)")
        if hot:
            ctr = [(round((i + .5) * cs, 1), round((j + .5) * cs, 1)) for i, j in hot[:4]]
            Wn.append(f"side {side}: {len(hot)} hotspot cells (≥{R['hotspot_fill']:.0%} filled with ≥{R['hotspot_neighbours']} crowded neighbours) around {ctr}")
            if free >= R["unbalanced_free_fraction"] * W * H:
                Wn.append(f"side {side}: unbalanced — hotspots while a {free:.0f} mm² free region exists at {bbox}; spread parts into it "
                          f"or declare it 'reserved'")
    return E, Wn, M
