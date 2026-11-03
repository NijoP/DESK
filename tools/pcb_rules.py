"""Apply PCB net classes and differential pairs from projects/<P>/pcb_rules.json, then read them back (verified).
Usage: python tools/pcb_rules.py projects/<product> [--dry]
pcb_rules.json:
  {"net_classes": {"PWR": ["VBUS","+3V3"], "USB": ["USB_DP","USB_DM"]},
   "diff_pairs":  {"USB_D": ["USB_DP","USB_DM"]},
   "equal_length": {"I2S": ["I2S_BCLK","I2S_WS","I2S_SD"]}}
Every net must exist on the PCB (checked first). Widths/clearances per class are set in EasyEDA's rule
configuration (docs/05_ROUTING.md); this tool makes the class membership deterministic and verifiable."""
import sys, os, json
from _common import ex, guard, load_project, check

proj = sys.argv[1]; P = load_project(proj)
R = json.load(open(os.path.join(proj, "pcb_rules.json")))
G = guard(P["pcb_uuid"])
have = set(check(ex(G + 'return await eda.pcb_Net.getAllNetsName();')) or [])
want = {n for v in R.get("net_classes", {}).values() for n in v} | {n for v in R.get("diff_pairs", {}).values() for n in v} \
     | {n for v in R.get("equal_length", {}).values() for n in v}
missing = sorted(want - have)
if missing: raise SystemExit(f"STOP: nets not on PCB: {missing} (update PCB from schematic first)")
if "--dry" in sys.argv: print(json.dumps(R, indent=1)); sys.exit(0)
js = G + '''const R=%s; const out={nc:[],dp:[],el:[]};
const exNC=(await eda.pcb_Drc.getAllNetClasses()||[]).map(c=>c.name||c.netClassName);
for(const [n,nets] of Object.entries(R.net_classes||{})){ if(exNC.includes(n)) await eda.pcb_Drc.deleteNetClass(n); out.nc.push([n,await eda.pcb_Drc.createNetClass(n,nets,null)]); }
const exDP=await eda.pcb_Drc.getAllDifferentialPairs(); const dpn=(Array.isArray(exDP)?exDP:Object.values(exDP||{})).map(d=>d.name||d.differentialPairName);
for(const [n,[p,m]] of Object.entries(R.diff_pairs||{})){ if(dpn.includes(n)) await eda.pcb_Drc.deleteDifferentialPair(n); out.dp.push([n,await eda.pcb_Drc.createDifferentialPair(n,p,m)]); }
const exEL=(await eda.pcb_Drc.getAllEqualLengthNetGroups()||[]).map(g=>g.name);
for(const [n,nets] of Object.entries(R.equal_length||{})){ if(exEL.includes(n)) await eda.pcb_Drc.deleteEqualLengthNetGroup(n); out.el.push([n,await eda.pcb_Drc.createEqualLengthNetGroup(n,nets,null)]); }
out.readback={nc:await eda.pcb_Drc.getAllNetClasses(), dp:await eda.pcb_Drc.getAllDifferentialPairs(), el:await eda.pcb_Drc.getAllEqualLengthNetGroups()};
return out;''' % json.dumps(R)
r = check(ex(js, timeout=120))
bad = [x for k in ("nc", "dp", "el") for x in r[k] if x[1] is not True]
print(json.dumps({k: r[k] for k in ("nc", "dp", "el")}))
rb = json.dumps(r["readback"])
notback = [n for n in list(R.get("net_classes", {})) + list(R.get("diff_pairs", {})) + list(R.get("equal_length", {})) if f'"{n}"' not in rb]
print("APPLIED + READ BACK" if not bad and not notback else f"FAIL: calls {bad}, not read back {notback}")
sys.exit(0 if not bad and not notback else 1)
