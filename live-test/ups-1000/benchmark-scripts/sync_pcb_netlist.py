"""API-only schematic -> PCB sync: export the schematic netlist file, load it into the PCB with pcb_Net.setNetlist,
then read back. Under desk.ops.write_op with a recorded approval. Refuses if the PCB already has components."""
import json, os, sys, time
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, ROOT)
from desk.bridge import ex
from desk import ops
P = "projects/UPS_1000"
pj = json.load(open(os.path.join(ROOT, P, "project.json")))
ntype = sys.argv[1] if len(sys.argv) > 1 else "JLCEDA"
ex("await eda.dmt_EditorControl.openDocument(%s); return 1;" % json.dumps(pj["sheet_uuid"]), project_path=P, timeout=30)
time.sleep(2)
net = ex('const f=await eda.sch_ManufactureData.getNetlistFile("ups.net"); return f? await f.text(): null;', project_path=P, timeout=60)
open(os.path.join(ROOT, "live-test/ups-1000/builder-records/sch_netlist.json"), "w", encoding="utf-8").write(net)
ex("await eda.dmt_EditorControl.openDocument(%s); return 1;" % json.dumps(pj["pcb_uuid"]), project_path=P, timeout=30)
time.sleep(3)
n0 = ex("const c=await eda.pcb_PrimitiveComponent.getAll(); return c?c.length:-1;", project_path=P, timeout=30)
if n0 != 0:
    sys.exit(f"REFUSED: PCB already has {n0} components")
aid = ops.record_approval(P, "pcb_set_netlist", pj["pcb_uuid"], granted_by="CAPTAIN (written benchmark authorisation)",
                          how="agent sync_pcb_netlist.py --allow-mutation", reason="API-only schematic->PCB sync (importChanges needs a human Apply)")
with ops.write_op(P, "pcb_set_netlist", pj["pcb_uuid"], classification=ops.OP_NON_IDEMPOTENT_MUTATION, approval=aid) as rec:
    rec["dirty"] = True
    r = ex("return await eda.pcb_Net.setNetlist(%s, %s);" % (json.dumps(ntype), json.dumps(net)), project_path=P, is_mutation=True, timeout=120)
    time.sleep(5)
    rec["dirty"] = False
out = ex("""const c=await eda.pcb_PrimitiveComponent.getAll(); let pads=0, netted=0; const nets=new Set();
for (const x of (c||[])) { const ps=x.getState_Pads()||[]; pads+=ps.length; for (const p of ps){ if(p.net){netted++; nets.add(p.net);} } }
return {n:c?c.length:-1, pads, netted, nets:nets.size};""", project_path=P, timeout=60)
print(json.dumps({"setNetlist": r, "type": ntype, "readback": out}))
