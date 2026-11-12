"""USB pair evidence from live readback: topology (branch points / stubs), lengths pad-to-pad, widths, spacing, vias."""
import sys, json, itertools
sys.path.insert(0, r"C:\nemotron test\Plotus\DESK")
from desk.copper_fill import pad_geometry, MIL
from shapely.geometry import Point, LineString
s = json.load(open(sys.argv[1])); out = {}
for net in ("USB_DP", "USB_DN"):
    T = [t for t in s["tracks"] if t["net"] == net]
    pads = {f'{p["ref"]}.{p["num"]}': pad_geometry(p) for p in s["pads"] if p["net"] == net}
    vias = [(round(v["x"] / MIL, 3), round(v["y"] / MIL, 3)) for v in s["vias"] if v["net"] == net]
    # nodes = rounded endpoints; attach endpoints inside a pad to that pad, and via endpoints to the via
    def node(x, y, layer):
        for name, g in pads.items():
            if g.buffer(0.01).contains(Point(x, y)): return name
        for v in vias:
            if abs(v[0] - x) < 0.02 and abs(v[1] - y) < 0.02: return f"via{v}"
        return f"L{layer}({x:.2f},{y:.2f})"
    adj, length, widths = {}, 0.0, set()
    for t in T:
        a = node(round(t["x1"] / MIL, 3), round(t["y1"] / MIL, 3), t["layer"]); b = node(round(t["x2"] / MIL, 3), round(t["y2"] / MIL, 3), t["layer"])
        L = LineString([(t["x1"] / MIL, t["y1"] / MIL), (t["x2"] / MIL, t["y2"] / MIL)]).length
        adj.setdefault(a, []).append((b, L)); adj.setdefault(b, []).append((a, L)); length += L; widths.add(round(t["w"] / MIL, 3))
    branch = {n: len(e) for n, e in adj.items() if len(e) >= 3 and not n.startswith(("J1", "U3", "U1", "TP"))}
    leaves = [n for n, e in adj.items() if len(e) == 1]
    # path length J1 -> U3 via Dijkstra
    import heapq
    src = [n for n in adj if n.startswith("J1")]; dst = [n for n in adj if n.startswith("U3")][0]
    dist = {n: 1e9 for n in adj}; pq = []
    for n in src: dist[n] = 0; heapq.heappush(pq, (0, n))
    while pq:
        d, n = heapq.heappop(pq)
        if d > dist[n]: continue
        for m, L in adj[n]:
            if d + L < dist[m]: dist[m] = d + L; heapq.heappush(pq, (d + L, m))
    out[net] = {"segments": len(T), "total_copper_mm": round(length, 2), "J1_to_U3_path_mm": round(dist[dst], 2),
                "widths_mm": sorted(widths), "vias": vias, "non_pad_branch_nodes": branch, "dangling_ends": [l for l in leaves if not l.startswith(("J1", "U3", "U1", "TP"))],
                "pads_on_net": sorted(pads)}
    print(net, json.dumps(out[net]))
print("length difference J1->U3: %.2f mm (limit 5)" % abs(out["USB_DP"]["J1_to_U3_path_mm"] - out["USB_DN"]["J1_to_U3_path_mm"]))
json.dump(out, open("../pcb/routing/usb_pair_check.json", "w"), indent=1)
