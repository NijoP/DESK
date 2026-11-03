"""THE acceptance test. Reads the live netlist and proves the sheet == the block specs.
Usage: python tools/verify.py projects/<product> [BLOCK_ID|all] [--json]
Checks per part: present, correct device, every pin on the spec net, NC flags set, no extra connected pins.
Sheet-wide: no unexpected nets (label collisions), no parts outside the specs, single-pin nets, fan-out.
Writes state/snapshot.json + state/netlist.net; on success a 'verified' ledger entry per block (spec+library hash)."""
import sys, os, json
from _common import ex, guard, load_project, check, S
from desk import ledger as LG, netcheck

READ_JS = r'''
const nl=await eda.sch_Netlist.getNetlist("Protel2"); const lines=nl.split(/\r?\n/); let cur=null; const pinNet={};
for(const ln of lines){const t=ln.trim(); if(t==="(")cur={pins:[]}; else if(t===")"){if(cur)for(const p of cur.pins)pinNet[p]=cur.name;cur=null;} else if(cur){if(!cur.name)cur.name=t; else cur.pins.push(t.split(' ')[0]);}}
const cs=await eda.sch_PrimitiveComponent.get(await eda.sch_PrimitiveComponent.getAllPrimitiveId()); const parts=[];
for(const c of cs){const ref=c.getState_Designator(); if(!ref)continue; const comp=c.getState_Component();
 const pins=(await eda.sch_PrimitiveComponent.getAllPinsByPrimitiveId(c.getState_PrimitiveId())).map(p=>({num:p.getState_PinNumber(),name:p.getState_PinName(),net:pinNet[ref+"-"+p.getState_PinNumber()]||null,nc:!!p.getState_NoConnected()}));
 parts.push({ref,dev:comp&&comp.name,x:c.getState_X(),y:c.getState_Y(),pins});}
return {nl,parts};'''


def read_sheet(P):
    return check(ex(guard(P["sheet_uuid"]) + READ_JS, timeout=600))


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    proj = args[0]; only = args[1] if len(args) > 1 and args[1] != "all" else None
    P = load_project(proj)
    snap = read_sheet(P)
    st = os.path.join(proj, "state"); os.makedirs(st, exist_ok=True)
    with open(os.path.join(st, "snapshot.json"), "w") as f: json.dump(snap["parts"], f, indent=1)
    with open(os.path.join(st, "netlist.net"), "w", encoding="utf-8") as f: f.write(snap["nl"])
    lib = S.load_library()
    blocks = S.load_blocks(proj)
    lay = os.path.join(st, "layout.json")
    built = set(json.load(open(lay))["blocks"]) if os.path.exists(lay) else set()
    ids = {only} if only else built
    E, nets, singles = netcheck.compare(blocks, ids, snap["parts"], lib)
    res = {"parts": len(snap["parts"]), "nets": len(nets), "single_pin_nets": singles, "errors": E,
           "fanout": {n: len(nets[n]) for n in sorted(nets, key=lambda n: -len(nets[n]))[:8]}}
    if "--json" in sys.argv:
        print(json.dumps(res))
    else:
        print(f"sheet: {res['parts']} parts, {res['nets']} nets | fan-out " + ", ".join(f"{k}:{v}" for k, v in res["fanout"].items()))
        print("single-pin nets (ok only if the other side is in a block not yet built):", singles or "none")
        for e in E: print("ERROR", e)
        print("VERIFIED" if not E else f"FAIL ({len(E)} errors)")
    if not E:
        for b in blocks:
            if b["id"] in ids:
                LG.add(proj, "verified", f"live netlist == spec ({len(b['parts'])} parts); sheet {res['parts']} parts / {res['nets']} nets",
                       block=b["id"], spec_hash=LG.block_hash(b, lib))
    sys.exit(1 if E else 0)
