"""Run 2b Stage 5: JLCPCB BOM with LCSC part numbers. Joins the live EasyEDA BOM export (designators / footprint /
MPN) to the block specs (schematic/desk/blocks/*.json: ref -> mpn, lcsc). Fails if a designator has no LCSC number
or if the spec MPN differs from the exported comment (no silent substitution).
Usage: python make_bom_lcsc.py <exported_bom.csv> <out.csv>"""
import sys, json, glob, csv, io
ROOT = r"C:\nemotron test\Plotus\run2\ESP32-S3-Development"
spec = {}
for f in glob.glob(ROOT + r"\schematic\desk\blocks\*.json"):
    for p in json.load(open(f, encoding="utf-8")).get("parts", []):
        if "ref" in p: spec[p["ref"]] = (p.get("mpn", ""), p.get("lcsc", ""), p.get("value", ""))
raw = open(sys.argv[1], "rb").read()
txt = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf-8-sig")
rows = list(csv.DictReader(io.StringIO(txt), delimiter="\t" if "\t" in txt.splitlines()[0] else ","))
out, bad = [], []
for r in rows:
    refs = [x.strip() for x in r["Designator"].split(",") if x.strip()]
    lc = {spec.get(x, ("", "", ""))[1] for x in refs}; mp = {spec.get(x, ("", "", ""))[0] for x in refs}
    if len(lc) != 1 or not next(iter(lc)): bad.append((refs, "LCSC missing/ambiguous", lc))
    if mp != {r["Comment"]}: bad.append((refs, "MPN mismatch", mp, r["Comment"]))
    out.append({"Comment": r["Comment"], "Designator": ",".join(refs), "Footprint": r["Footprint"], "LCSC Part #": ",".join(sorted(lc)),
                "Quantity": len(refs)})
with open(sys.argv[2], "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(out[0])); w.writeheader(); w.writerows(out)
print(f"{len(out)} lines, {sum(o['Quantity'] for o in out)} parts, issues: {bad or 'none'}")
sys.exit(1 if bad else 0)
