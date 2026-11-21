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
from desk.reliability.mutation import cli_approve
APPROVAL = None if "--dry" in sys.argv else cli_approve(proj, "pcb_rules", P["pcb_uuid"])   # policy check before any bridge call
R = json.load(open(os.path.join(proj, "pcb_rules.json")))
G = guard(P["pcb_uuid"])
have = set(check(ex(G + 'return await eda.pcb_Net.getAllNetsName();', window_id=P.get("window_id"))) or [])
want = {n for v in R.get("net_classes", {}).values() for n in v} | {n for v in R.get("diff_pairs", {}).values() for n in v} \
     | {n for v in R.get("equal_length", {}).values() for n in v}
missing = sorted(want - have)
if missing: raise SystemExit(f"STOP: nets not on PCB: {missing} (update PCB from schematic first)")
if "--dry" in sys.argv: print(json.dumps(R, indent=1)); sys.exit(0)
from desk.reliability.mutation import MutationSpec, run_live, report

W = P.get("window_id")
js = G + '''const R=%s; const out={nc:[],dp:[],el:[]};
const exNC=(await eda.pcb_Drc.getAllNetClasses()||[]).map(c=>c.name||c.netClassName);
for(const [n,nets] of Object.entries(R.net_classes||{})){ if(exNC.includes(n)) await eda.pcb_Drc.deleteNetClass(n); out.nc.push([n,await eda.pcb_Drc.createNetClass(n,nets,null)]); }
const exDP=await eda.pcb_Drc.getAllDifferentialPairs(); const dpn=(Array.isArray(exDP)?exDP:Object.values(exDP||{})).map(d=>d.name||d.differentialPairName);
for(const [n,[p,m]] of Object.entries(R.diff_pairs||{})){ if(dpn.includes(n)) await eda.pcb_Drc.deleteDifferentialPair(n); out.dp.push([n,await eda.pcb_Drc.createDifferentialPair(n,p,m)]); }
const exEL=(await eda.pcb_Drc.getAllEqualLengthNetGroups()||[]).map(g=>g.name);
for(const [n,nets] of Object.entries(R.equal_length||{})){ if(exEL.includes(n)) await eda.pcb_Drc.deleteEqualLengthNetGroup(n); out.el.push([n,await eda.pcb_Drc.createEqualLengthNetGroup(n,nets,null)]); }
return out;''' % json.dumps(R)
# Independent readback (separate script): the names of the net classes, differential pairs and equal-length groups.
READ_JS = G + '''const L=x=>(Array.isArray(x)?x:Object.values(x||{}));
return {net_classes:L(await eda.pcb_Drc.getAllNetClasses()).map(c=>c.name||c.netClassName),
 diff_pairs:L(await eda.pcb_Drc.getAllDifferentialPairs()).map(d=>d.name||d.differentialPairName),
 equal_length:L(await eda.pcb_Drc.getAllEqualLengthNetGroups()).map(g=>g.name)};'''
expected = {k: sorted(R.get(k, {})) for k in ("net_classes", "diff_pairs", "equal_length") if R.get(k)}
if not expected: print("nothing to apply: pcb_rules.json lists no net class, differential pair or group"); sys.exit(0)
spec = MutationSpec(op="pcb_rules", target=P["pcb_uuid"], document_uuid=P["pcb_uuid"], verifier="names_present",
                    expected=expected, methods=["eda.pcb_Drc.deleteNetClass", "eda.pcb_Drc.createNetClass",
                                                "eda.pcb_Drc.deleteDifferentialPair", "eda.pcb_Drc.createDifferentialPair",
                                                "eda.pcb_Drc.deleteEqualLengthNetGroup", "eda.pcb_Drc.createEqualLengthNetGroup"],
                    approval=APPROVAL, readback_attempts=1, readback_interval_s=1.0)
calls = {}
def _execute():
    calls.update(check(ex(js, timeout=120, window_id=W)) or {})
    return calls
res = run_live(proj, P, lambda c: check(ex(c, window_id=W)), spec, _execute, lambda: check(ex(READ_JS, timeout=120, window_id=W)) or {})
bad = [x for k in ("nc", "dp", "el") for x in calls.get(k, []) if x[1] is not True]
print(json.dumps({k: calls.get(k, []) for k in ("nc", "dp", "el")}))
rc = report(res)
print("APPLIED + READ BACK" if not bad and rc == 0 else f"FAIL: calls {bad}, readback verified {res.verified}")
sys.exit(0 if not bad and rc == 0 else 1)
