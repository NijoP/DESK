"""Read back every PCB component: position, rotation, layer, footprint, bbox and pads (with nets).
Usage: python tools/pcb_dump.py projects/<product>   -> state/pcb_dump.json   (units: mil, EasyEDA PCB frame)
This is the input for placement planning and for tools/pcb_check.py."""
import sys, os, json
from _common import ex, guard, load_project, check

proj = sys.argv[1]
P = load_project(proj)
G = guard(P["pcb_uuid"])
ids = check(ex(G + 'const cs=await eda.pcb_PrimitiveComponent.get(await eda.pcb_PrimitiveComponent.getAllPrimitiveId());'
                   'return cs.map(c=>[c.getState_PrimitiveId(),c.getState_Designator()]);'))
out = {}
for i in range(0, len(ids), 40):
    chunk = [x[0] for x in ids[i:i + 40]]
    r = check(ex(G + '''const res={}; for(const id of %s){ const c=await eda.pcb_PrimitiveComponent.get(id); const x=c.getState_X(),y=c.getState_Y();
 const pads=await eda.pcb_PrimitiveComponent.getAllPinsByPrimitiveId(id)||[]; const b=await eda.pcb_Primitive.getPrimitivesBBox([id]);
 res[c.getState_Designator()]={id,x,y,rot:c.getState_Rotation(),layer:c.getState_Layer(),fp:(c.getState_Footprint()||{}).name,
  bbox:[b.minX-x,b.maxX-x,b.minY-y,b.maxY-y],
  pads:pads.map(p=>({num:p.getState_PadNumber(),dx:p.getState_X()-x,dy:p.getState_Y()-y,shape:p.getState_Pad(),rot:p.getState_Rotation(),net:p.getState_Net(),layer:p.getState_Layer()}))}; } return res;''' % json.dumps(chunk)))
    out.update(r); print(f"{len(out)}/{len(ids)}")
os.makedirs(os.path.join(proj, "state"), exist_ok=True)
json.dump(out, open(os.path.join(proj, "state", "pcb_dump.json"), "w"), indent=0)
print("saved state/pcb_dump.json")
