"""Independent Gerber/drill inspection with gerbonara (not EasyEDA). Counts board-outline rectangles,
reports panel bbox, per-layer bbox, drill hit counts. Usage: python tools_inspect_gerber.py <gerber.zip> <report.json>"""
import sys, os, json, zipfile, re, tempfile, math
from gerbonara import LayerStack
from gerbonara.rs274x import GerberFile
from gerbonara.excellon import ExcellonFile

zpath, report = sys.argv[1], sys.argv[2]
tmp = tempfile.mkdtemp(prefix="gerb_")
with zipfile.ZipFile(zpath) as z:
    z.extractall(tmp)
files = sorted(os.listdir(tmp))
out = {"zip": zpath, "files": files, "layers": {}, "drills": {}, "outline": {}}

def bbox_of(f):
    try:
        (x0, y0), (x1, y1) = f.bounding_box(unit="mm")
        return [round(x0, 3), round(y0, 3), round(x1, 3), round(y1, 3)]
    except Exception as e:
        return str(e)

for fn in files:
    p = os.path.join(tmp, fn)
    low = fn.lower()
    try:
        if low.endswith((".drl", ".txt", ".xln", ".exc")) or "drill" in low:
            ef = ExcellonFile.open(p)
            holes = [o for o in ef.objects]
            diam = {}
            for o in holes:
                d = round(getattr(o, "diameter", 0) or 0, 3)
                diam[d] = diam.get(d, 0) + 1
            out["drills"][fn] = {"hits": len(holes), "by_diameter_mm": diam, "bbox": bbox_of(ef), "plated": getattr(ef, "plated", None)}
        elif low.endswith((".gbr", ".gtl", ".gbl", ".gto", ".gbo", ".gts", ".gbs", ".gko", ".gm1", ".g1", ".g2", ".gtp", ".gbp", ".gml")):
            gf = GerberFile.open(p)
            n = len(gf.objects)
            out["layers"][fn] = {"objects": n, "bbox": bbox_of(gf)}
            if "outline" in low or low.endswith((".gko", ".gm1")):
                # count axis-aligned closed rectangles formed by line segments
                segs = []
                for o in gf.objects:
                    if o.__class__.__name__ == "Line":
                        segs.append((round(o.x1, 3), round(o.y1, 3), round(o.x2, 3), round(o.y2, 3)))
                xs = sorted({s[0] for s in segs} | {s[2] for s in segs})
                ys = sorted({s[1] for s in segs} | {s[3] for s in segs})
                out["outline"][fn] = {"segments": len(segs), "distinct_x": xs, "distinct_y": ys}
    except Exception as e:
        out["layers"][fn] = {"error": str(e)}

json.dump(out, open(report, "w"), indent=1)
print(json.dumps(out, indent=1)[:6000])
