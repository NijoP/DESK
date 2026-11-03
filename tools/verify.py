"""THE acceptance test. Reads the live netlist and proves the sheet == the block specs.
Usage: python tools/verify.py projects/<product> [BLOCK_ID|all]
Checks per part: present, correct device, every pin on the spec net, NC flags set.
Checks sheet-wide: no unexpected nets (label collisions / merges), single-pin nets, fan-out of power nets.
Writes state/snapshot.json + state/netlist.net. Exit 0 only when clean."""
import sys, os, json, collections
from _common import ex, guard, load_project, check, S
from desk import ledger as LG

proj = sys.argv[1]; only = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] != "all" else None
P = load_project(proj)
snap = check(ex(guard(P["sheet_uuid"]) + r'''
const nl=await eda.sch_Netlist.getNetlist("Protel2"); const lines=nl.split(/\r?\n/); let cur=null; const pinNet={};
for(const ln of lines){const t=ln.trim(); if(t==="(")cur={pins:[]}; else if(t===")"){if(cur)for(const p of cur.pins)pinNet[p]=cur.name;cur=null;} else if(cur){if(!cur.name)cur.name=t; else cur.pins.push(t.split(' ')[0]);}}
const cs=await eda.sch_PrimitiveComponent.get(await eda.sch_PrimitiveComponent.getAllPrimitiveId()); const parts=[];
for(const c of cs){const ref=c.getState_Designator(); if(!ref)continue; const comp=c.getState_Component();
 const pins=(await eda.sch_PrimitiveComponent.getAllPinsByPrimitiveId(c.getState_PrimitiveId())).map(p=>({num:p.getState_PinNumber(),name:p.getState_PinName(),net:pinNet[ref+"-"+p.getState_PinNumber()]||null,nc:!!p.getState_NoConnected()}));
 parts.push({ref,dev:comp&&comp.name,uuid:comp&&comp.uuid,x:c.getState_X(),y:c.getState_Y(),pins});}
return {nl,parts};''', timeout=600))
os.makedirs(os.path.join(proj, "state"), exist_ok=True)
json.dump(snap["parts"], open(os.path.join(proj, "state", "snapshot.json"), "w"), indent=1)
open(os.path.join(proj, "state", "netlist.net"), "w", encoding="utf-8").write(snap["nl"])

lib = S.load_library()
live = {p["ref"]: p for p in snap["parts"]}
blocks = [b for b in S.load_blocks(proj) if not only or b["id"] == only]
built = json.load(open(os.path.join(proj, "state", "layout.json")))["blocks"] if os.path.exists(os.path.join(proj, "state", "layout.json")) else {}
E, spec_nets = [], collections.Counter()
for b in S.load_blocks(proj):
    for p in b["parts"]:
        for net in p.get("pins", {}).values(): spec_nets[net] += 1
for b in blocks:
    if not only and b["id"] not in built: continue
    for p in b["parts"]:
        r = p["ref"]; L = live.get(r)
        if not L: E.append(f"{b['id']}: {r} missing on sheet"); continue
        want = lib.get(p["mpn"], {}).get("name", p["mpn"])
        if L["dev"] and want and L["dev"] != want: E.append(f"{r}: device {L['dev']} != spec {want}")
        lp = {q["num"]: q for q in L["pins"]}
        for num, net in p.get("pins", {}).items():
            got = lp.get(num, {}).get("net")
            if got != net: E.append(f"{r}.{num}({lp.get(num, {}).get('name')}): net {got} != spec {net}")
        for num in p.get("nc", []):
            if not lp.get(num, {}).get("nc"): E.append(f"{r}.{num}: NC flag missing")
# sheet-wide net audit
nets = collections.defaultdict(list)
for p in snap["parts"]:
    for q in p["pins"]:
        if q["net"]: nets[q["net"]].append(f"{p['ref']}.{q['num']}")
built_nets = {n for b in S.load_blocks(proj) if b["id"] in built for p in b["parts"] for n in p.get("pins", {}).values()}
for n in nets:
    if n not in spec_nets: E.append(f"unexpected net {n} on {nets[n][:6]} -> label collision or stray wire")
singles = sorted(n for n, ps in nets.items() if len(ps) == 1)
print(f"sheet: {len(snap['parts'])} parts, {len(nets)} nets")
print("power/ground fan-out:", ", ".join(f"{n}:{len(nets[n])}" for n in sorted(nets, key=lambda n: -len(nets[n]))[:8]))
print("single-pin nets (ok only if the other side is in a block not yet built):", singles or "none")
for e in E: print("ERROR", e)
print("VERIFIED" if not E else f"FAIL ({len(E)} errors)")
if not E:
    for b in blocks:
        if only or b["id"] in built:
            LG.add(proj, "verified", f"live netlist == spec ({len(b['parts'])} parts); sheet {len(snap['parts'])} parts / {len(nets)} nets",
                   block=b["id"], spec_hash=LG.block_hash(b))
sys.exit(1 if E else 0)
