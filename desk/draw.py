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
  if(r===180)L=Math.min(L,x-ST[1]-10); if(r===0)R=Math.max(R,x+ST[1]+n); if(r===270)B=Math.min(B,y-ST[1]-n); if(r===90)T=Math.max(T,y+ST[1]+n);}
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
    """The `labels` wiring style: one script places the block, stubs + labels every pin, draws the frame."""
    return _fill(BLOCK_JS, block, lib, x0, yt, pin_counts)


def _fill(template, block, lib, x0, yt, pin_counts):
    parts = []
    for p in block["parts"]:
        d = lib[p["mpn"]]
        parts.append({"ref": p["ref"], "lib": d["libraryUuid"], "uuid": d["uuid"], "kind": p.get("kind"),
                      "npins": pin_counts.get(p["mpn"], len(p.get("pins", {})) + len(p.get("nc", []))),
                      "map": p.get("pins", {}), "nc": p.get("nc", [])})
    spec = {"title": block["title"], "parts": parts}
    return (template.replace("__STYLE__", json.dumps(STYLE)).replace("__SPEC__", json.dumps(spec))
            .replace("__X0__", str(x0)).replace("__YT__", str(yt)))


# ------------------------------------------------------------------ `subsystem` wiring style (docs/02, rule S11)
# Two phases so the wire router is plain, offline-tested Python (desk/schematic_router.py):
#   1. PLACE_JS  places the parts exactly as BLOCK_JS does (same spacing code) and sets NC flags, but draws no
#                stubs, labels or frame; it returns every pin tip (x, y, rotation) of every placed part.
#   2. desk.schematic_router plans orthogonal wires for local / interface nets and stubs + labels for rails;
#      desk.schematic_io.subsystem_draw_js draws the plan plus the frame and title (UNVERIFIED-LIVE adapter).
# PLACE_JS is derived from BLOCK_JS by exact substitutions so the placement can never drift between the styles.
def _derive(src, edits):
    for old, new, count in edits:
        if src.count(old) != count:
            raise AssertionError(f"desk/draw.py: BLOCK_JS changed, cannot derive PLACE_JS ({old[:40]!r} x{src.count(old)})")
        src = src.replace(old, new)
    return src


PLACE_JS = _derive(BLOCK_JS, [
    ("const ics=SPEC.parts.filter(isIC)",
     'const PINS={}; async function pinsOf(id){return (await eda.sch_PrimitiveComponent.getAllPinsByPrimitiveId(id))'
     '.map(p=>({num:""+p.getState_PinNumber(),x:p.getState_X(),y:p.getState_Y(),rot:+p.getState_Rotation()}));}\n'
     "const ics=SPEC.parts.filter(isIC)", 1),
    ("await labelPins(id,p.map);", "PINS[p.ref]=await pinsOf(id);", 2),
    ("await eda.sch_PrimitiveRectangle.create(X0,YT,W,H,0,0,S.frame_color,null,1,null,null);\n", "", 1),
    ("await eda.sch_PrimitiveText.create(X0+20,YT-45,SPEC.title,0,S.frame_color,null,S.title_size,true,false,false);\n", "", 1),
    ("return {W,H,REF};", "return {W,H,REF,PINS};", 1),
    # wires need every pin on the 10-unit grid: snap the part origins and the passive row pitch (125 -> 130);
    # label widths (5.5 per character) would otherwise push ICs and the passive grid off it
    ("ROWH=S.row_h;", "ROWH=Math.ceil(S.row_h/10)*10; const G10=v=>Math.floor(v/10)*10;", 1),
    ("const nx=X0+3000+(cx-e.L), ny=YT-3000+((YT-TITLE)-e.T);",
     "const nx=G10(X0+3000+(cx-e.L)), ny=G10(YT-3000+((YT-TITLE)-e.T));", 1),
    ("let y=(ics.length?rowB:YT-TITLE)-90, i=0;", "let y=G10((ics.length?rowB:YT-TITLE)-90), i=0;", 1),
])
GRID_UNITS = 10         # subsystem placement origin grid (x0 / yt are snapped to it by tools/build.py)

ROUTE_MARGIN = 300      # extra room right of / below the placed parts that in-block wires may use

# Appearance of the `subsystem` style (owner's style spec, section 1), as data. STYLE above stays the `labels` style
# byte-for-byte. Extend by adding a key here AND a row in SUBSYSTEM_STYLE_APPLIED saying how it reaches the sheet.
SUBSYSTEM_STYLE = {
    "background": "#FFFFFF",          # white sheet
    "frame_color": "#1F3A68",         # thin rectangular subsystem boundary (dark blue)
    "frame_line_width": 1,
    "title_color": "#1F3A68",         # subsystem title, top-left, bold, prominent
    "title_size": 12,
    "title_bold": True,
    "reference_color": "#1F3A68",     # component designators (dark blue)
    "label_color": "#1F4FBF",         # net labels (blue)
    "label_size": 5,
    "ground_color": "#000000",        # ground nets / symbols (black)
    "wire_color": "#008000",          # electrical wires (green)
    "junction_dots": True,            # a dot wherever three or more same-net wire ends meet
    "junction_color": "#008000",
    "junction_radius": 3,
}
# How each key reaches the sheet. "drawn": a call DESK already uses in production (frame / text / label creation).
# "UNVERIFIED-LIVE": emitted by desk.schematic_io's adapter inside try/catch; a refusal is counted, never fatal, and
# can never change connectivity. "not applied": no API call is known; recorded so the requirement is not lost.
SUBSYSTEM_STYLE_APPLIED = {
    "background": "not applied: EasyEDA's sheet background is an editor theme setting (white by default)",
    "frame_color": "drawn", "frame_line_width": "drawn", "title_color": "drawn", "title_size": "drawn",
    "title_bold": "drawn", "label_size": "drawn",
    "reference_color": "not applied: no known API sets a designator colour",
    "label_color": "UNVERIFIED-LIVE", "ground_color": "UNVERIFIED-LIVE", "wire_color": "UNVERIFIED-LIVE",
    "junction_dots": "UNVERIFIED-LIVE", "junction_color": "UNVERIFIED-LIVE", "junction_radius": "UNVERIFIED-LIVE",
}


def place_js(block, lib, x0, yt, pin_counts):
    """Phase 1 of the `subsystem` style: place + NC flags only; returns {W, H, REF, PINS:{ref:[{num,x,y,rot}]}}."""
    return _fill(PLACE_JS, block, lib, x0, yt, pin_counts)


def routing_window(x0, yt, W, H):
    """Where in-block wires may run: inside the block's column (never left of x0, never into the title band)."""
    return (x0 + 10, yt - H - ROUTE_MARGIN, x0 + W + ROUTE_MARGIN, yt - STYLE["title_h"])


def frame_of(plan, x0, yt, W, H):
    """Frame that encloses the placed parts, every wire and every label text: [x, y_top, W, H]."""
    from desk.schematic_router import CHAR_W
    xs, ys = [x0 + W], [yt - H]
    for s in plan.get("segments", []):
        xs += [s["a"][0], s["b"][0]]; ys += [s["a"][1], s["b"][1]]
    for lab in plan.get("labels", []):
        n = len(lab["net"]) * CHAR_W
        x, y = lab["at"]
        if lab["rotation"] == 90:
            ys += [y - n, y + n]; xs.append(x)
        else:
            xs.append(x + n); ys.append(y)
    right, bottom = max(xs) + 40, min(ys) - 40
    return [x0, yt, max(W, right - x0), max(H, yt - bottom)]


def plan_svg(plan, style=None, scale=1.0):
    """Deterministic SVG preview of a wiring plan in the subsystem style (offline review and visual-regression
    snapshots). Symbols are the checker's outline model, not the library symbol."""
    from xml.sax.saxutils import escape
    from desk.schematic_router import text_box
    st = style or SUBSYSTEM_STYLE
    x, yt, W, H = plan.get("frame") or [0, 0, 0, 0]
    pad = 20
    vx, vy, vw, vh = x - pad, -(yt + pad), W + 2 * pad, H + 2 * pad
    f = lambda v: f"{v:g}"  # noqa: E731
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{f(vx)} {f(vy)} {f(vw)} {f(vh)}" '
           f'width="{f(vw * scale)}" height="{f(vh * scale)}">',
           f'<rect x="{f(vx)}" y="{f(vy)}" width="{f(vw)}" height="{f(vh)}" fill="{st["background"]}"/>',
           f'<rect x="{f(x)}" y="{f(-yt)}" width="{f(W)}" height="{f(H)}" fill="none" stroke="{st["frame_color"]}" '
           f'stroke-width="{st["frame_line_width"]}"/>',
           f'<text x="{f(x + 20)}" y="{f(-(yt - 45))}" font-size="{st["title_size"]}" fill="{st["title_color"]}" '
           f'font-weight="{"bold" if st["title_bold"] else "normal"}" font-family="sans-serif">'
           f'{escape(plan.get("title", ""))}</text>']
    for ref, (x0, y0, x1, y1) in sorted((plan.get("bodies") or {}).items()):
        out.append(f'<rect x="{f(x0)}" y="{f(-y1)}" width="{f(x1 - x0)}" height="{f(y1 - y0)}" fill="none" '
                   f'stroke="#555555" stroke-width="1"/>')
        out.append(f'<text x="{f(x0)}" y="{f(-y1 - 3)}" font-size="6" fill="{st["reference_color"]}" '
                   f'font-family="sans-serif">{escape(ref)}</text>')
    ground = lambda n: n in ("GND", "AGND", "DGND", "PGND") or n.endswith("_GND")  # noqa: E731
    for s in plan.get("segments", []):
        out.append(f'<line x1="{f(s["a"][0])}" y1="{f(-s["a"][1])}" x2="{f(s["b"][0])}" y2="{f(-s["b"][1])}" '
                   f'stroke="{st["wire_color"]}" stroke-width="1.5"/>')
    for j in plan.get("junctions", []) if st.get("junction_dots") else []:
        out.append(f'<circle cx="{f(j["at"][0])}" cy="{f(-j["at"][1])}" r="{st["junction_radius"]}" '
                   f'fill="{st["junction_color"]}"/>')
    for lab in plan.get("labels", []):
        x0, y0, x1, y1 = text_box(lab)
        colour = st["ground_color"] if ground(lab["net"]) else st["label_color"]
        rot = f' transform="rotate(-90 {f(x1)} {f(-y0)})"' if lab.get("rotation") == 90 else ""
        tx, ty = (x0, -y0) if not rot else (x1, -y0)
        out.append(f'<text x="{f(tx)}" y="{f(ty)}" font-size="{st["label_size"]}" fill="{colour}" '
                   f'font-family="monospace"{rot}>{escape(lab["net"])}</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def plan_subsystem(block, blocks, placed, x0, yt, project_json=None):
    """Phase 2 planning (pure): classify the block's nets and route them over the phase-1 pin read-back.
    `placed` is PLACE_JS's return value. Client requirements: block 'label_nets' forces nets to labels."""
    from desk import spec as S
    from desk import schematic_router as R
    classes = S.classify_nets(block, blocks, (project_json or {}).get("rails", []))
    plan = R.plan_block(block, placed["PINS"], classes, routing_window(x0, yt, placed["W"], placed["H"]),
                        STYLE["stub"], force_labels=block.get("label_nets", []))
    plan["frame"] = frame_of(plan, x0, yt, placed["W"], placed["H"])
    plan["title"] = block["title"]
    return plan
