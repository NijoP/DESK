"""Remove ONE block from the sheet: its parts plus every wire / text / rectangle inside its recorded frame.
Usage: python tools/clear_block.py projects/<product> <BLOCK_ID>
Only touches the area recorded in state/layout.json. Other blocks are never touched.
If the API cannot remove net labels on your EasyEDA version, the tool tells you; delete them by box-select."""
import sys, os, json
from _common import ex, guard, load_project, check, S

from desk import ops
proj, bid = sys.argv[1], sys.argv[2]
P = load_project(proj)
st_file = os.path.join(proj, "state", "layout.json")
st = json.load(open(st_file)) if os.path.exists(st_file) else {"blocks": {}}
f = st["blocks"].get(bid)
if f is None:   # half-drawn block from a failed build: frame unknown -> remove by designator only
    f = {"x": -10 ** 6, "y": -10 ** 6, "W": 0, "H": 0}
    print(f"{bid} not in layout state: removing its parts by designator only (wires/labels of a failed build may remain)")
refs = [p["ref"] for p in S.find_block(proj, bid)["parts"]]
box = [f["x"] - 5, f["x"] + f["W"] + 5, f["y"] - f["H"] - 5, f["y"] + 5]
js = guard(P["sheet_uuid"]) + '''
const REFS=%s, B=%s; const inb=(x,y)=>x>=B[0]&&x<=B[1]&&y>=B[2]&&y<=B[3]; const out={};
const cs=await eda.sch_PrimitiveComponent.get(await eda.sch_PrimitiveComponent.getAllPrimitiveId());
const pc=cs.filter(c=>REFS.includes(c.getState_Designator())).map(c=>c.getState_PrimitiveId()); if(pc.length) await eda.sch_PrimitiveComponent.delete(pc); out.parts=pc.length;
try{const ws=await eda.sch_PrimitiveWire.get(await eda.sch_PrimitiveWire.getAllPrimitiveId());
 const d=ws.filter(w=>{const raw=w.getState_Line(); if(!raw) return false; const l=Array.isArray(raw[0])?raw.flat():raw; return inb(l[0],l[1]);}).map(w=>w.getState_PrimitiveId()); if(d.length) await eda.sch_PrimitiveWire.delete(d); out.wires=d.length;}catch(e){out.wires="ERR "+e;}
try{const ts=await eda.sch_PrimitiveText.get(await eda.sch_PrimitiveText.getAllPrimitiveId());
 const d=ts.filter(t=>inb(t.getState_X(),t.getState_Y())).map(t=>t.getState_PrimitiveId()); if(d.length) await eda.sch_PrimitiveText.delete(d); out.texts=d.length;}catch(e){out.texts="ERR "+e;}
try{const rs=await eda.sch_PrimitiveRectangle.get(await eda.sch_PrimitiveRectangle.getAllPrimitiveId());
 const d=rs.filter(r=>Math.abs(r.getState_TopLeftX()-B[0]-5)<2&&Math.abs(r.getState_TopLeftY()-B[3]+5)<2).map(r=>r.getState_PrimitiveId()); if(d.length) await eda.sch_PrimitiveRectangle.delete(d); out.rects=d.length;}catch(e){out.rects="ERR "+e;}
return out;''' % (json.dumps(refs), json.dumps(box))
for p in [p for p in ops.pending(proj) if p["target"] == bid]:
    ops.resolve_pending(proj, p["id"], "clear_block started")
with ops.write_op(proj, "clear", bid, force_unlock="--force-unlock" in sys.argv) as rec:
    rec["dirty"] = True
    print(check(ex(js, window_id=P.get("window_id"))))
    st["blocks"].pop(bid, None)
    os.makedirs(os.path.dirname(st_file), exist_ok=True)
    with open(st_file, "w") as h: json.dump(st, h, indent=1)
print(f"cleared {bid}. Rebuild with: python tools/build.py {proj} {bid} --at {f['x']} {f['y']}")
