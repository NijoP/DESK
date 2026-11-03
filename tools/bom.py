"""Build the BOM straight from the block specs (schematic and BOM are the same data) and audit it.
Usage: python tools/bom.py projects/<product> [--qty 1000]
Writes projects/<P>/bom.csv (grouped by MPN). Warnings:
  - passive without value / rating / package, part without lcsc
  - capacitor rating voltage < 1.5x the highest rail it touches (rail voltage parsed from net names like +3V3, +5V0, VBUS=5V)
  - value used only once (candidate to merge into the preferred passive set)
  - more than 2 passive package sizes on the board"""
import sys, os, re, csv, collections
from _common import S

proj = sys.argv[1]
W = []
rows = collections.OrderedDict()
pkgs = collections.Counter()
values = collections.Counter()
RAIL_V = {"VBUS": 5.5, "USB_VBUS": 5.5, "VBAT": 4.2, "VSYS": 4.5}


def rail_v(net):
    if net in RAIL_V: return RAIL_V[net]
    m = re.match(r"^\+?(\d+)V(\d*)", net)
    return float(f"{m.group(1)}.{m.group(2) or 0}") if m else None


for b in S.load_blocks(proj):
    for p in b["parts"]:
        ref, mpn = p["ref"], p.get("mpn", "?")
        passive = re.match(r"^(R|C|L|FB|D|LED)\d", ref) is not None
        if not p.get("lcsc"): W.append(f"{ref}: no lcsc code")
        if passive:
            for k in ("value", "rating", "package"):
                if not p.get(k): W.append(f"{ref} ({b['id']}): passive missing '{k}'")
            if p.get("package"): pkgs[p["package"]] += 1
            if p.get("value"): values[(ref[0], p["value"])] += 1
        if ref.startswith("C") and p.get("rating"):
            m = re.search(r"(\d+(?:\.\d+)?)\s*V", p["rating"])
            vmax = max([v for v in (rail_v(n) for n in p.get("pins", {}).values()) if v] or [0])
            if m and vmax and float(m.group(1)) < 1.5 * vmax:
                W.append(f"{ref}: rated {m.group(1)} V on a {vmax} V rail (< 1.5x, check DC-bias derating)")
        key = mpn
        if key not in rows:
            rows[key] = {"mpn": mpn, "lcsc": p.get("lcsc", ""), "value": p.get("value", ""), "rating": p.get("rating", ""),
                         "package": p.get("package", ""), "refs": [], "blocks": set()}
        rows[key]["refs"].append(ref); rows[key]["blocks"].add(b["id"])
for (t, v), n in values.items():
    if n == 1: W.append(f"value {v} ({t}) used once - can it use the preferred set?")
if len(pkgs) > 2: W.append(f"{len(pkgs)} passive package sizes used: {dict(pkgs)} - standardise if possible")
out = os.path.join(proj, "bom.csv")
with open(out, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["Qty", "Designators", "MPN", "LCSC", "Value", "Rating", "Package", "Blocks"])
    for r in rows.values():
        w.writerow([len(r["refs"]), " ".join(sorted(r["refs"])), r["mpn"], r["lcsc"], r["value"], r["rating"], r["package"], " ".join(sorted(r["blocks"]))])
for x in W: print("WARN ", x)
print(f"{sum(len(r['refs']) for r in rows.values())} parts, {len(rows)} unique lines -> {out}")
