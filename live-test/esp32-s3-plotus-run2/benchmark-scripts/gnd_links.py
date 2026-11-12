"""Run 2b Stage 3: plan explicit GND links so GND is connected by tracks/pads/fills WITHOUT relying on a via-to-fill join
(run 1 lesson: EasyEDA DRC does not reliably join a via to an API pcb_PrimitiveFill).
Model: objects = GND fills (recomputed), pads, tracks, vias (+ the extra plan items); a via joins tracks/pads but NOT fills.
For every group other than the main one, try a straight or one-bend bottom-layer link (clearance >= CLR to other-net
bottom copper) from any via / bottom-reachable point of that group to a main-group via or THT pad.
Usage: python gnd_links.py snapshot.json extra_plan.json out_plan.json"""
import sys, json, itertools
sys.path.insert(0, r"C:\nemotron test\Plotus\DESK")
from desk.copper_fill import compute_plane_fill, pad_geometry, MIL
from shapely.geometry import Point, LineString
from shapely.ops import unary_union

s = json.load(open(sys.argv[1])); extra = json.load(open(sys.argv[2])); out = sys.argv[3]
CLR, TW, MAXL = 0.2, 0.3, 20.0
plan = json.load(open("../schematic/desk/placement.json", encoding="utf-8"))
bw, bh = plan["board_mm"]; board = [(0, 0), (bw, 0), (bw, bh), (0, bh)]
kos = [k["rect_mm"] for k in plan.get("keepouts", []) + plan.get("copper_keepouts", []) if "rect_mm" in k]
N = "GND"


def build(extra_items):
    objs = []   # (name, layers, geom, kind, anchor_points_on_bottom)
    tr = list(s["tracks"]) + [{"net": t["net"], "layer": t["layer"], "w": t["w"] * MIL, "x1": t["pts"][0][0] * MIL, "y1": t["pts"][0][1] * MIL,
                               "x2": t["pts"][-1][0] * MIL, "y2": t["pts"][-1][1] * MIL, "id": "new"} for t in extra_items["tracks"]]
    vi = list(s["vias"]) + [{"net": v["net"], "x": v["xy"][0] * MIL, "y": v["xy"][1] * MIL, "d": v.get("d", 0.6) * MIL} for v in extra_items["vias"]]
    for L in (1, 2):
        for i, p in enumerate(compute_plane_fill(L, N, board, s["pads"], tr, vi, keepouts_mm=kos, clearance_mm=0.3)["polygons"]):
            objs.append((f"fill{L}.{i}", {L}, p, "fill", []))
    for p in s["pads"]:
        if p["net"] == N:
            tht = p["layer"] == 12
            objs.append((f'{p["ref"]}.{p["num"]}', {1, 2} if tht else {p["layer"]}, pad_geometry(p), "pad", [(p["x"] / MIL, p["y"] / MIL)] if tht else []))
    for k, t in enumerate(tr):
        if t["net"] == N:
            a, b = (t["x1"] / MIL, t["y1"] / MIL), (t["x2"] / MIL, t["y2"] / MIL)
            ln = LineString([a, b]); n = max(1, int(ln.length / 0.5))
            pts = [ln.interpolate(i / n, normalized=True).coords[0] for i in range(n + 1)] if t["layer"] == 2 else []
            objs.append((f'trk{k}', {t["layer"]}, ln.buffer(t["w"] / MIL / 2), "track", pts))
    for v in vi:
        if v["net"] == N:
            c = (v["x"] / MIL, v["y"] / MIL)
            objs.append((f'via({c[0]:.2f},{c[1]:.2f})', {1, 2}, Point(c).buffer(v["d"] / MIL / 2), "via", [c]))
    par = list(range(len(objs)))
    def f(i):
        while par[i] != i: par[i] = par[par[i]]; i = par[i]
        return i
    for i, j in itertools.combinations(range(len(objs)), 2):
        a, b = objs[i], objs[j]
        if not (a[1] & b[1]) or {a[3], b[3]} == {"via", "fill"}: continue
        if a[2].intersects(b[2]): par[f(i)] = f(j)
    groups = {}
    for i in range(len(objs)): groups.setdefault(f(i), []).append(objs[i])
    gs = sorted(groups.values(), key=lambda g: (sum(1 for o in g if o[3] == "pad"), len(g)), reverse=True)
    return gs, tr, vi


def obstacles(tr, vi):
    g = [pad_geometry(p) for p in s["pads"] if p["net"] != N and p["layer"] in (2, 12)]
    g += [LineString([(t["x1"] / MIL, t["y1"] / MIL), (t["x2"] / MIL, t["y2"] / MIL)]).buffer(t["w"] / MIL / 2) for t in tr if t["net"] != N and t["layer"] == 2]
    g += [Point(v["x"] / MIL, v["y"] / MIL).buffer(v["d"] / MIL / 2) for v in vi if v["net"] != N]
    g += [Point(p["x"] / MIL, p["y"] / MIL).buffer(1.7) for p in s["pads"] if p.get("ref", "").startswith("MH")]   # NPTH holes
    return unary_union(g)


def inside_board(pts):
    return all(0.6 <= x <= bw - 0.6 and 0.6 <= y <= bh - 0.6 for x, y in pts) and \
        not any(k[0] < x < k[2] and k[1] < y < k[3] for x, y in pts for k in kos if k[0] > 60)   # antenna keep-out


items = {"tracks": list(extra.get("tracks", [])), "vias": list(extra.get("vias", []))}
for it in range(12):
    gs, tr, vi = build(items)
    print(f"iter {it}: {len(gs)} groups; main has {sum(1 for o in gs[0] if o[3]=='pad')} pads")
    if len(gs) == 1: break
    obs = obstacles(tr, vi)
    targets = [a for o in gs[0] for a in o[4]]
    linked = False
    for g in gs[1:]:
        starts = [a for o in g for a in o[4]]
        if not starts:
            print("   no bottom anchor in group", [o[0] for o in g][:6]); continue
        best = None
        for sp, tp in itertools.product(starts, targets):
            d = Point(sp).distance(Point(tp))
            if d < 0.05 or d > MAXL: continue
            for path in ([sp, tp], [sp, (sp[0], tp[1]), tp], [sp, (tp[0], sp[1]), tp]):
                if len(path) == 3 and (abs(sp[0] - tp[0]) < 0.05 or abs(sp[1] - tp[1]) < 0.05): continue
                if not inside_board(path): continue
                ln = LineString(path)
                if ln.buffer(TW / 2).distance(obs) >= CLR and (best is None or ln.length < best[0]):
                    best = (ln.length, path)
        if best:
            items["tracks"].append({"net": N, "layer": 2, "w": TW, "pts": [[round(x, 3), round(y, 3)] for x, y in best[1]],
                                    "why": "explicit bottom GND link for group " + ",".join(o[0] for o in g if o[3] == "pad")[:80]})
            print("   link", [o[0] for o in g if o[3] in ("pad", "via")][:6], "len %.2f" % best[0], best[1])
            linked = True
            break            # rebuild groups after each link (new copper changes obstacles and membership)
        else:
            print("   NO LINK for", [o[0] for o in g][:6])
    if not linked: break
gs, tr, vi = build(items)
print("FINAL groups", len(gs), [[o[0] for o in g][:5] for g in gs[1:]])
# split multi-point tracks into segments for remed_apply
segs = []
for t in items["tracks"]:
    for a, b in zip(t["pts"], t["pts"][1:]):
        segs.append({k: v for k, v in t.items() if k != "pts"} | {"pts": [a, b]})
json.dump({"note": "run 2b Stage 3 explicit GND links (gnd_links.py)", "min_clearance_mm": 0.16, "tracks": segs, "vias": items["vias"]}, open(out, "w"), indent=1)
print("wrote", out, len(segs), "segments", len(items["vias"]), "vias")
