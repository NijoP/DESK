"""Schematic -> PCB sync attempt via the documented API (INC-20261111-006): save schematic, importChanges, readback.
Mutation goes through desk.ops.write_op with a recorded approval (agent run under Captain's written authorisation)."""
import json, os, sys, time
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, ROOT)
from desk.bridge import ex
from desk import ops
P = "projects/UPS_1000"
pj = json.load(open(os.path.join(ROOT, P, "project.json")))
aid = ops.record_approval(P, "pcb_import_changes", pj["pcb_uuid"], granted_by="CAPTAIN (written benchmark authorisation)",
                          how="agent live-test/ups-1000/benchmark-scripts/sync_pcb.py --allow-mutation", reason="UPS_1000 S2 schematic->PCB sync")
def count():
    return ex("const c=await eda.pcb_PrimitiveComponent.getAll(); return c?c.length:-1;", project_path=P)
with ops.write_op(P, "pcb_import_changes", pj["pcb_uuid"], classification=ops.OP_IDEMPOTENT_MUTATION, approval=aid) as rec:
    rec["dirty"] = True
    r1 = ex("return await eda.sch_Document.save();", project_path=P, is_mutation=True)
    r2 = ex("await eda.dmt_EditorControl.openDocument(%s); return true;" % json.dumps(pj["pcb_uuid"]), project_path=P, is_mutation=True)
    time.sleep(3)
    before = count()
    r3 = ex("return await eda.pcb_Document.importChanges(%s);" % json.dumps(pj["pcb_uuid"]), project_path=P, is_mutation=True)
    time.sleep(8)
    after = count()
    rec["dirty"] = False
print(json.dumps({"sch_save": r1, "open_pcb": r2, "pcb_components_before": before, "importChanges_returned": r3, "pcb_components_after_8s": after}))
