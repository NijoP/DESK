"""The DESK schematic style, as code. One call = one framed, titled subsystem block:

   +-- TITLE --------------------------------------------+
   |  [IC1]--LABEL   [IC2]--LABEL   [CONN]--LABEL         |   ICs / connectors in one row, left->right
   |                                                      |
   |  [R1]-NET  [R2]-NET  [C1]-NET  [C2]-NET              |   passives in a grid underneath
   +------------------------------------------------------+

Every pin gets a short REAL wire stub + a net label at its end (never a floating label).
Stub lengths alternate (short/long) between neighbouring pins so labels never touch / merge.
Units: EasyEDA schematic units (0.01 in). Everything lands on the 100-mil grid of the symbol pins.
Change the look ONLY via STYLE below, so every product looks the same.
"""
import json

STYLE = {
    "frame_color": "#2E5E8C",   # block rectangle + title colour
    "title_size": 12,           # block title font
    "label_size": 5,            # net label font
    "stub": [110, 170],         # alternating stub lengths for IC pins (short, long)
    "pad": 60,                  # inner margin of the frame
    "title_h": 90,              # space reserved for the title
    "gap_x": 120,               # gap between ICs in the IC row
    "pitch": 400,               # passive grid column pitch
    "row_h": 125,               # passive grid row pitch
    "block_gap": 150,           # gap between blocks on the sheet
}

BLOCK_JS = r'''
const S=__STYLE__; const SPEC=__SPEC__; const X0=__X0__, YT=__YT__;
const CH=5.5, ST=S.stub, PAD=S.pad, TITLE=S.title_h, GAPX=S.gap_x, PITCH=S.pitch, ROWH=S.row_h;
function isIC(p){ if(p.kind) return p.kind!=="passive"; return p.npins>4 || (/^(U|FPC|J|H|USB|CN|DC|Q|SW|BT|Y|X)\d/.test(p.ref) && p.npins>2); }
async function labelPins(id,map){
 const pins=await eda.sch_PrimitiveComponent.getAllPinsByPrimitiveId(id); const g={};
 for(const p of pins){const r=""+p.getState_Rotation();(g[r]=g[r]||[]).push(p);}
 for(const r of Object.keys(g)){const arr=g[r];
  if(r==="180"||r==="0")arr.sort((a,b)=>b.getState_Y()-a.getState_Y()); else arr.sort((a,b)=>a.getState_X()-b.getState_X());
  for(let k=0;k<arr.length;k++){const p=arr[k];const net=map[p.getState_PinNumber()]; if(net==null)continue;
   const x=p.getState_X(),y=p.getState_Y(),R=+r,s=ST[k%2]; let ex=x,ey=y,lr=0;
   if(R===180)ex=x-s; else if(R===0)ex=x+s; else if(R===270){ey=y-(s-30);lr=90;} else {ey=y+(s-30);lr=90;}
   await eda.sch_PrimitiveWire.create([x,y,ex,ey],net);
   const L=await eda.sch_PrimitiveAttribute.createNetLabel(ex,ey,net);
   try{await eda.sch_PrimitiveAttribute.modify(L.getState_PrimitiveId(),{rotation:lr,fontSize:S.label_size});}catch(e){}}}}
async function ext(id,map){const ps=await eda.sch_PrimitiveComponent.getAllPinsByPrimitiveId(id);let L=1e9,R=-1e9,T=-1e9,B=1e9;
 for(const p of ps){const x=p.getState_X(),y=p.getState_Y(),r=p.getState_Rotation(),n=(map[p.getState_PinNumber()]||"").length*CH;
  L=Math.min(L,x);R=Math.max(R,x);T=Math.max(T,y);B=Math.min(B,y);
  if(r===180)L=Math.min(L,x-ST[1]-10-n); if(r===0)R=Math.max(R,x+ST[1]+n); if(r===270)B=Math.min(B,y-ST[1]-n); if(r===90)T=Math.max(T,y+ST[1]+n);}
 return {L:L-40,R:R+40,T:T+40,B:B-40};}
async function nc(id,list){if(!list.length)return;const ps=await eda.sch_PrimitiveComponent.getAllPinsByPrimitiveId(id);
 for(const p of ps){if(list.includes(p.getState_PinNumber())){p.setState_NoConnected(true);await p.done();}}}
const ics=SPEC.parts.filter(isIC), pas=SPEC.parts.filter(p=>!isIC(p));
let cx=X0+PAD, rowB=YT-TITLE, maxR=X0+PAD; const REF={};
for(const p of ics){
 const c=await eda.sch_PrimitiveComponent.create({libraryUuid:p.lib,uuid:p.uuid},X0+3000,YT-3000,"",0,false,true,true); const id=c.getState_PrimitiveId();
 const e=await ext(id,p.map); const nx=X0+3000+(cx-e.L), ny=YT-3000+((YT-TITLE)-e.T);
 await eda.sch_PrimitiveComponent.modify(id,{x:nx,y:ny,designator:p.ref}); const e2=await ext(id,p.map);
 await labelPins(id,p.map); await nc(id,p.nc); REF[p.ref]=id; cx=e2.R+GAPX; maxR=Math.max(maxR,e2.R); rowB=Math.min(rowB,e2.B);}
const icW=Math.max(maxR-X0, 2*PITCH+PAD);
const cols=Math.max(2,Math.min(5,Math.floor((icW-PAD)/PITCH)));
let y=(ics.length?rowB:YT-TITLE)-90, i=0;
for(const p of pas){const col=i%cols,row=Math.floor(i/cols);const x=X0+PAD+170+col*PITCH, yy=y-row*ROWH;
 const c=await eda.sch_PrimitiveComponent.create({libraryUuid:p.lib,uuid:p.uuid},x,yy,"",0,false,true,true); const id=c.getState_PrimitiveId();
 await eda.sch_PrimitiveComponent.modify(id,{designator:p.ref}); await labelPins(id,p.map); await nc(id,p.nc); REF[p.ref]=id; i++;}
const rows=Math.ceil(pas.length/cols); const bottom=pas.length? y-(rows-1)*ROWH-80 : rowB-20;
const W=Math.max(icW+PAD, cols*PITCH+PAD+40), H=YT-bottom;
await eda.sch_PrimitiveRectangle.create(X0,YT,W,H,0,0,S.frame_color,null,1,null,null);
await eda.sch_PrimitiveText.create(X0+20,YT-45,SPEC.title,0,S.frame_color,null,S.title_size,true,false,false);
return {W,H,REF};
'''


def block_js(block, lib, x0, yt, pin_counts):
    parts = []
    for p in block["parts"]:
        d = lib[p["mpn"]]
        parts.append({"ref": p["ref"], "lib": d["libraryUuid"], "uuid": d["uuid"], "kind": p.get("kind"),
                      "npins": pin_counts.get(p["mpn"], len(p.get("pins", {})) + len(p.get("nc", []))),
                      "map": p.get("pins", {}), "nc": p.get("nc", [])})
    spec = {"title": block["title"], "parts": parts}
    return (BLOCK_JS.replace("__STYLE__", json.dumps(STYLE)).replace("__SPEC__", json.dumps(spec))
            .replace("__X0__", str(x0)).replace("__YT__", str(yt)))
