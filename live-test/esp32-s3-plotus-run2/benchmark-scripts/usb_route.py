"""Run 2b Stage 3: hand-designed USB D+/D- chain + U1 GND escape, written as PROTECTED wiring for Freerouting.
Topology (no branches except the disclosed U1 pin-2 tap):
  DP: J1 A6+B6 -> U1 pin1 (flow-through: in from below, out east) -> 45deg/vertical/east run -> TP7 (in-line) -> U3 pin14 (IO20)
  DN: J1 A7+B7 -> via -> bottom under U1 -> via V_DN -> {top: U1 pin2 tap ~0.8 mm} -> east run -> TP8 (in-line) -> U3 pin13 (IO19)
  Pair: w 0.254 mm (10 mil), pitch 0.5 mm, top layer over the bottom GND plane, 45-degree chamfers.
Usage: python usb_route.py snapshot.json [--write-dsn in.dsn out.dsn]"""
import sys, json
sys.path.insert(0, r"C:\nemotron test\Plotus\DESK")
from desk.copper_fill import pad_geometry, MIL
from shapely.geometry import Point, LineString, box
from shapely.ops import unary_union

W = 0.254
TP7, TP8 = (49.78, 33.2), (51.05, 36.4)          # in-line WAYPOINTS on the drops (TP8 = pad centre, rot 90).
# Final Stage 3 placement: TP7 pad centre (49.1, 33.2) rot 0 (2.8 x 1.5 mm, x 47.7..50.5), so the D+ drop at x=49.78
# runs through the pad. Rot 90 at x=49.78 overlapped U3/TP8 bodies (gate). 3V3 rerouted west of it (plan_3v3_tp7.json).
GV = (10.3, 22.6)                                  # GND via for U1 pins 3/8
V_DN_J1, V_DN = (9.2, 21.85), (13.1, 21.5)

segs = []   # (net, layer, width, [pts])
def path(net, layer, pts, w=W): segs.append((net, layer, w, [tuple(map(float, p)) for p in pts]))

# --- J1 fan-outs (kept from Freerouting's clearance-valid result) ---
path("USB_DP", 1, [(7.673, 22.25), (6.79, 22.25), (6.79, 21.25), (7.673, 21.25)], 0.15)   # A6 <-> B6 behind the pads
path("USB_DN", 1, [(7.673, 22.751), (8.45, 22.751), (8.75, 22.45), (8.75, 22.05), V_DN_J1], 0.15)  # B7 -> via
path("USB_DN", 1, [(7.673, 21.75), (8.75, 21.75), V_DN_J1], 0.15)                                 # A7 -> via
# --- DP: J1 -> U1 pin 1 (enter from below) -> east ---
path("USB_DP", 1, [(7.673, 21.25), (9.0, 21.25), (10.15, 20.1), (12.0, 20.1), (12.0, 21.001)])
path("USB_DP", 1, [(12.0, 21.001), (12.6, 21.0), (13.0, 20.6), (20.707, 20.6), (21.5, 21.393), (21.5, 35.4), (22.0, 35.9),
                   (49.28, 35.9), (49.78, 35.4), TP7, (49.784, 30.749)])
# --- DN: J1 via -> bottom -> V_DN -> top ---
path("USB_DN", 2, [V_DN_J1, V_DN])
path("USB_DN", 1, [(11.999, 21.501), V_DN])                                     # U1 pin 2 tap (disclosed)
path("USB_DN", 1, [V_DN, (13.5, 21.1), (20.5, 21.1), (21.0, 21.6), (21.0, 35.607), (21.793, 36.4), TP8, (51.054, 30.749)])
vias = [("USB_DN", V_DN_J1), ("USB_DN", V_DN), ("GND", GV)]
# --- U1 GND: pin 8 <-> pin 3 under the package, pin 8 -> left -> via ---
path("GND", 1, [(12.0, 22.0), (11.2, 22.0), (10.7, 22.0), GV], 0.2)

if __name__ == "__main__":
    s = json.load(open(sys.argv[1]))
    pads = [p for p in s["pads"] if p.get("ref") not in ("TP7", "TP8")]
    def tp_pad(c, net): return {"net": net, "layer": 1, "geom": box(c[0] - 0.75, c[1] - 1.4, c[0] + 0.75, c[1] + 1.4)}
    newpads = [tp_pad(TP7, "USB_DP"), tp_pad(TP8, "USB_DN")]
    ok = True
    for net, L, w, pts in segs:
        g = LineString(pts).buffer(w / 2)
        obs = [pad_geometry(p) for p in pads if p["net"] != net and p["layer"] in (L, 12)] + \
              [q["geom"] for q in newpads if q["net"] != net and L == 1]
        obs += [LineString(p2).buffer(w2 / 2) for n2, L2, w2, p2 in segs if n2 != net and L2 == L]
        obs += [Point(v).buffer(0.305) for n2, v in vias if n2 != net]
        d = g.distance(unary_union(obs))
        print(f"{net:7s} L{L} {len(pts)} pts  clearance {d:.3f} mm", "OK" if d >= 0.152 else "FAIL"); ok &= d >= 0.152
    for net, v in vias:
        g = Point(v).buffer(0.305)
        obs = [pad_geometry(p) for p in pads if p["net"] != net] + [q["geom"] for q in newpads if q["net"] != net]
        obs += [LineString(p2).buffer(w2 / 2) for n2, L2, w2, p2 in segs if n2 != net]
        d = g.distance(unary_union(obs)); print(f"via {net} {v} clearance {d:.3f}", "OK" if d >= 0.152 else "FAIL"); ok &= d >= 0.152
    # lengths J1 (B6 / A7 junction) -> U3 pad, along the chain
    def L(pts): return LineString(pts).length
    dp = L([(9.0, 21.25), (10.15, 20.1), (12.0, 20.1), (12.0, 21.001)]) + L(segs[4][3]) + (9.0 - 7.673)
    dn = L([(7.673, 21.75), (8.75, 21.75), V_DN_J1]) + L([V_DN_J1, V_DN]) + L(segs[7][3]) + 1.6 * 0.0  # via barrel ignored
    print(f"length DP {dp:.2f} mm  DN {dn:.2f} mm  diff {abs(dp-dn):.2f} mm (limit 5)")
    print("ALL OK" if ok else "CLEARANCE FAIL")
    if "--write-dsn" in sys.argv:
        i = sys.argv.index("--write-dsn"); src, dst = sys.argv[i + 1], sys.argv[i + 2]
        d = open(src, encoding="utf-8").read()
        lay = {1: "TopLayer", 2: "BottomLayer"}
        wires = ""
        for net, Ly, w, pts in segs:
            coords = " ".join(f"{x * MIL:.2f} {y * MIL:.2f}" for x, y in pts)
            wires += f"    (wire (path {lay[Ly]} {w * MIL:.2f} {coords}) (net {net}) (type protect))\n"
        for net, (x, y) in vias:
            wires += f"    (via via0 {x * MIL:.2f} {y * MIL:.2f} (net {net}) (type protect))\n"
        assert "(wiring)" in d
        d = d.replace("(wiring)", "(wiring\n" + wires + "  )")
        open(dst, "w", encoding="utf-8").write(d); print("DSN with protected wiring ->", dst)
