"""Import a Freerouting SES into the live PCB with the exact Phase-15 code of DESK tools/route.py, then run
DESK's PhysicalConnectivityVerifier (Phase 19). Used because Freerouting 2.1.0 only writes a SES when run
directly (DESK's supervised run stops it on stagnation before it writes one; F-014).
Usage: python ses_import_verify.py <ses> [--no-import]"""
import sys, os, json, base64
DESK = r"C:\nemotron test\Plotus\DESK"
sys.path.insert(0, DESK); sys.path.append(os.path.join(DESK, "tools"))
os.chdir(DESK)
from desk.bridge import ex, guard, load_project, check
from desk import ops
from desk.routing import PhysicalConnectivityVerifier

proj = r"..\run2\ESP32-S3-Development\schematic\desk"
P = load_project(proj); W = P["window_id"]; G = guard(P["pcb_uuid"])
ses = sys.argv[1]
if "--no-import" not in sys.argv:
    b64 = base64.b64encode(open(ses, "rb").read()).decode()
    with ops.write_op(proj, "route_import", "PCB") as rec:
        rec["dirty"] = True
        js = ('const lines = await eda.pcb_PrimitiveLine.getAll(); const lineIds = lines.map(l => l.primitiveId);'
              'if (lineIds.length > 0) await eda.pcb_PrimitiveLine.delete(lineIds);'
              'const vias = await eda.pcb_PrimitiveVia.getAll(); const viaIds = vias.map(v => v.primitiveId);'
              'if (viaIds.length > 0) await eda.pcb_PrimitiveVia.delete(viaIds);'
              'const b=atob("%s"); const u=new Uint8Array(b.length); for(let i=0;i<b.length;i++)u[i]=b.charCodeAt(i);'
              'const ok=await eda.pcb_Document.importAutoRouteSesFile(new File([u],"desk_route.ses")); await eda.pcb_Document.save(); return ok;' % b64)
        r = check(ex(G + js, timeout=600, window_id=W, is_mutation=True))
    print("SES import:", r)
dump = json.load(open(os.path.join(proj, "state", "pcb_dump.json"), encoding="utf-8"))
tracks = ex(G + 'return (await eda.pcb_PrimitiveLine.getAll()).map(l=>({id:l.primitiveId,net:l.net,x1:l.startX,y1:l.startY,x2:l.endX,y2:l.endY,width:l.lineWidth,layer:l.layer}));', timeout=120, window_id=W) or []
vias = ex(G + 'return (await eda.pcb_PrimitiveVia.getAll()).map(v=>({id:v.primitiveId,net:v.net,x:v.x,y:v.y,diameter:v.diameter,start_layer:v.startLayer,end_layer:v.endLayer}));', timeout=120, window_id=W) or []
out_dir = r"..\run2\ESP32-S3-Development\pcb\routing"
json.dump({"tracks": tracks, "vias": vias}, open(os.path.join(out_dir, "routing_readback.json"), "w"), indent=0)
zones = []
if "--with-fills" in sys.argv:   # live pcb_PrimitiveFill copper (API plane fills) as conductor zones: outer ring of each piece
    fl = ex(G + 'return (await eda.pcb_PrimitiveFill.getAll()).map(f=>({net:f.getState_Net(),layer:f.getState_Layer(),poly:f.getState_ComplexPolygon().polygon}));', timeout=120, window_id=W) or []
    def rings(a):
        if a and isinstance(a[0], list): return [r for x in a for r in rings(x)]
        nums = [v for v in a if isinstance(v, (int, float))]
        return [[[nums[i], nums[i + 1]] for i in range(0, len(nums) - 1, 2)]]
    for f in fl:
        rr = rings(f["poly"])
        if rr: zones.append({"net": f["net"], "layer": f["layer"], "polygon": rr[0]})
    print("fill zones", len(zones))
res = PhysicalConnectivityVerifier.verify_board(pcb_dump=dump, tracks=tracks, vias=vias, zones=zones)
print("tracks", len(tracks), "vias", len(vias))
print("Physical Connectivity:", res.summary)
bad = {}
for attr in ("net_results", "results", "nets"):
    v = getattr(res, attr, None)
    if v:
        for k, n in (v.items() if isinstance(v, dict) else [(getattr(x, "net", "?"), x) for x in v]):
            st = getattr(n, "status", None) or (n.get("status") if isinstance(n, dict) else None)
            if st and "FULL" not in str(st).upper() and "CONNECTED" != str(st).upper():
                bad[k] = {"status": str(st), "missing": getattr(n, "disconnected_pads", None) or getattr(n, "unconnected_pads", None) or (n.get("disconnected_pads") if isinstance(n, dict) else None)}
        break
print("not fully connected:", json.dumps(bad, default=str)[:1500])
json.dump({"summary": res.summary, "not_connected": bad}, open(os.path.join(out_dir, "connectivity_report.json"), "w"), indent=1, default=str)
