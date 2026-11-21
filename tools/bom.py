"""Build the BOM straight from the block specs (schematic and BOM are the same data) and audit it.
Usage: python tools/bom.py projects/<product> [--qty 1000]
Writes projects/<P>/bom.csv (grouped by MPN). Warnings:
  - passive without value / rating / package, part without lcsc
  - capacitor rating voltage < 1.5x the highest rail it touches (rail voltage parsed from net names like +3V3, +5V0, VBUS=5V)
  - value used only once (candidate to merge into the preferred passive set)
  - more than 2 passive package sizes on the board

Sourcing (roadmap I-5): python tools/bom.py projects/<P> --sourcing [--qty N] [--evidence FILE ...]
    [--allow-backorder] [--live-lcsc] [--preferred robu,lcsc] [--fx INR=0.012]
  Selects every line in-stock-first (Robu/LCSC preferred, JLCPCB parts library for assembly), checks
  alternatives for footprint and electrical equivalence and writes projects/<P>/sourcing_report.json
  and SOURCING_REPORT.md. Evidence: projects/<P>/sourcing/evidence/*.json plus every --evidence file
  (format: desk/component_intelligence/suppliers/evidence.py). Offline unless --live-lcsc (keyless
  LCSC detail reads by C-number). Unverified stock is reported as STOCK_UNKNOWN, never in stock.
  Exit 0 when the verdict is VERIFIED, 2 when INCOMPLETE."""
import sys, os, re, csv, collections, argparse, glob, json
from _common import S

ap = argparse.ArgumentParser(description="Build and audit the BOM; optional in-stock-first sourcing report.")
ap.add_argument("project")
ap.add_argument("--qty", type=int, default=1, help="boards to build (sourcing quantity multiplier)")
ap.add_argument("--sourcing", action="store_true", help="also write the verified component selection report")
ap.add_argument("--evidence", action="append", default=[], help="browser-agent evidence JSON file (repeatable)")
ap.add_argument("--allow-backorder", action="store_true", help="client permits backordered parts")
ap.add_argument("--live-lcsc", action="store_true", help="read LCSC public detail pages by C-number (network)")
ap.add_argument("--preferred", default="robu,lcsc", help="preferred suppliers in order")
ap.add_argument("--fx", action="append", default=[], help="currency rate to USD, e.g. INR=0.012")
args = ap.parse_args()
proj = args.project
W = []
rows = collections.OrderedDict()
pkgs = collections.Counter()
values = collections.Counter()
RAIL_V = {"VBUS": 5.5, "USB_VBUS": 5.5, "VBAT": 4.2, "VSYS": 4.5}


def rail_v(net):
    if net in RAIL_V: return RAIL_V[net]
    m = re.match(r"^\+?(\d+)V(\d*)", net)
    return float(f"{m.group(1)}.{m.group(2) or 0}") if m else None


all_parts = []
for b in S.load_blocks(proj):
    for p in b["parts"]:
        all_parts.append(p)
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


def _sourcing():
    from desk.component_intelligence.procurement.selection import SourcingPolicy, build_sourcing_report
    from desk.component_intelligence.suppliers.evidence import EvidenceStore, EvidenceSupplierProvider
    from desk.component_intelligence.suppliers.providers.lcsc.client import LcscApiClient
    from desk.component_intelligence.suppliers.providers.lcsc.provider import LcscSupplierProvider
    from desk.component_intelligence.suppliers.providers.robu import RobuSupplierProvider
    from desk.component_intelligence.suppliers.registry import SupplierRegistry
    from desk.manufacturing.jlcpcb.parts_library import JlcpcbPartsProvider

    store = EvidenceStore()
    files = sorted(glob.glob(os.path.join(proj, "sourcing", "evidence", "*.json"))) + list(args.evidence)
    ingest = {"accepted": 0, "rejected": [], "files": files}
    for f in files:
        rep = store.load_file(f)
        ingest["accepted"] += rep.accepted
        ingest["rejected"] += rep.rejected
    reg = SupplierRegistry()
    reg.register(RobuSupplierProvider(store))
    client = None
    if args.live_lcsc:
        client = LcscApiClient(use_offline_fixtures=False)
        reg.register(LcscSupplierProvider(client=client, evidence=store))
    else:
        reg.register(EvidenceSupplierProvider("lcsc", "LCSC Electronics", store))
    reg.register(JlcpcbPartsProvider(store))
    fx = {}
    for item in args.fx:
        cur, _, rate = item.partition("=")
        fx[cur.strip().upper()] = float(rate)
    policy = SourcingPolicy(preferred_suppliers=tuple(x.strip() for x in args.preferred.split(",") if x.strip()),
                            allow_backorder=args.allow_backorder, fx_to_base=fx)
    lims = [] if args.live_lcsc else ["LCSC was not read live (offline run); only evidence files were used."]
    report = build_sourcing_report(all_parts, reg, policy, batch_quantity=args.qty, evidence=ingest,
                                   limitations=lims, project=os.path.basename(os.path.normpath(proj)))
    if client is not None:
        report.limitations.extend(client.limitations)
    with open(os.path.join(proj, "sourcing_report.json"), "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, indent=2)
    with open(os.path.join(proj, "SOURCING_REPORT.md"), "w", encoding="utf-8") as f:
        f.write(report.to_markdown() + "\n")
    acc = report.acceptance()
    print(f"SOURCING {report.verdict}: {acc['lines_in_stock']}/{acc['lines_total']} lines in stock, "
          f"{acc['lines_with_compatible_alternative_only']} with a compatible alternative only, "
          f"{acc['backordered_selections_without_permission']} backordered without permission, "
          f"{ingest['accepted']} evidence records ({len(ingest['rejected'])} rejected) -> "
          f"{os.path.join(proj, 'SOURCING_REPORT.md')}")
    return 0 if report.verdict == "VERIFIED" else 2


if args.sourcing:
    sys.exit(_sourcing())
