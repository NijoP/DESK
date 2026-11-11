"""Deterministic schematic read-back and wiring for EasyEDA Pro (fix for "the bridge has no read ops").

The API gateway executes arbitrary JavaScript, and the getters below are the ones DESK has used
in production (`tools/verify.py`, `desk/draw.py`): `sch_PrimitiveComponent.getAllPrimitiveId/get`,
`getAllPinsByPrimitiveId`, pin `getState_X/Y/Rotation/PinNumber/PinName/NoConnected`,
`sch_Netlist.getNetlist("Protel2")`, `sch_PrimitiveWire.create([x,y,x2,y2], net)` and
`sch_PrimitiveAttribute.createNetLabel(x, y, net)`.

A model never needs pin coordinates: it names pins as `REF.PIN`, DESK reads the sheet, resolves the
coordinates, and wires in the DESK style (a stub wire from each pin plus a net label), which is how
`tools/build.py` connects nets. No coordinates are ever guessed; unknown pins are refused.

Zero external dependencies.
"""
from __future__ import annotations
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from desk.fsutil import atomic_write_json

READ_JS = r'''
let nl=""; const pinNet={};
try { nl=await eda.sch_Netlist.getNetlist("Protel2"); const lines=nl.split(/\r?\n/); let cur=null;
  for(const ln of lines){const t=ln.trim(); if(t==="(")cur={pins:[]}; else if(t===")"){if(cur)for(const p of cur.pins)pinNet[p]=cur.name;cur=null;} else if(cur){if(!cur.name)cur.name=t; else cur.pins.push(t.split(' ')[0]);}}
} catch(e) { nl="ERR:"+e; }
const ids=await eda.sch_PrimitiveComponent.getAllPrimitiveId(); const cs=await eda.sch_PrimitiveComponent.get(ids); const parts=[];
for(const c of cs){const ref=c.getState_Designator(); if(!ref)continue; const comp=c.getState_Component(); const id=c.getState_PrimitiveId();
 const pins=(await eda.sch_PrimitiveComponent.getAllPinsByPrimitiveId(id)).map(p=>({num:""+p.getState_PinNumber(),name:p.getState_PinName(),x:p.getState_X(),y:p.getState_Y(),rot:p.getState_Rotation(),net:pinNet[ref+"-"+p.getState_PinNumber()]||null,nc:!!p.getState_NoConnected()}));
 parts.push({ref,uuid:id,dev:comp&&comp.name,x:c.getState_X(),y:c.getState_Y(),rot:c.getState_Rotation(),pins});}
return {parts, netlist_ok: !String(nl).startsWith("ERR:"), netlist: String(nl).slice(0, 200000)};'''

STUB_LENGTHS = (40, 60)   # alternating stub lengths as in desk/draw.py STYLE.stub


def _num(v: float) -> float:
    """Integral floats print as ints so the generated JS matches hand-written DESK calls."""
    return int(v) if float(v).is_integer() else v


def pin_exit(x: float, y: float, rot: float, stub: float) -> Tuple[float, float, int]:
    """Where a stub wire from a pin ends and the label rotation, following desk/draw.py's convention."""
    r = int(rot) % 360
    if r == 180:
        return _num(x - stub), _num(y), 0
    if r == 0:
        return _num(x + stub), _num(y), 0
    if r == 270:
        return _num(x), _num(y - (stub - 30)), 90
    return _num(x), _num(y + (stub - 30)), 90


def parse_pin_ref(token: str) -> Tuple[str, str]:
    m = re.match(r"^\s*([A-Za-z][A-Za-z0-9_]*)[.\-:]([A-Za-z0-9_]+)\s*$", token or "")
    if not m:
        raise ValueError(f"pin reference '{token}' must look like REF.PIN (e.g. U1.3)")
    return m.group(1), m.group(2)


def find_pin(dump: Dict[str, Any], ref: str, pin: str) -> Optional[Dict[str, Any]]:
    for part in dump.get("parts", []):
        if part.get("ref") == ref:
            for p in part.get("pins", []):
                if str(p.get("num")) == str(pin) or (p.get("name") and str(p.get("name")) == str(pin)):
                    return {**p, "ref": ref, "uuid": part.get("uuid")}
            return None
    return None


def plan_net_wires(dump: Dict[str, Any], net: str, pin_refs: List[str]) -> Dict[str, Any]:
    """Resolve REF.PIN names against the sheet and plan DESK-style stub wires + net labels.
    Refuses unknown pins and pins already on a different net. Pure function (no ECAD call)."""
    if not net or not re.match(r"^[A-Za-z0-9_+\-./]+$", net):
        raise ValueError("net name must be non-empty and contain only [A-Za-z0-9_+-./]")
    wires, labels, skipped, errors = [], [], [], []
    for i, token in enumerate(pin_refs):
        ref, pin = parse_pin_ref(token)
        p = find_pin(dump, ref, pin)
        if p is None:
            avail = next((sorted(str(q["num"]) for q in part["pins"]) for part in dump.get("parts", []) if part.get("ref") == ref), None)
            errors.append(f"{ref}.{pin}: " + ("component not on sheet" if avail is None else f"no such pin; available: {avail[:40]}"))
            continue
        if p.get("nc"):
            errors.append(f"{ref}.{pin}: marked no-connect")
            continue
        if p.get("net") == net:
            skipped.append(f"{ref}.{pin} already on {net}")
            continue
        if p.get("net") and p.get("net") != net:
            errors.append(f"{ref}.{pin}: already on net {p['net']}; refusing to re-net without explicit clear")
            continue
        stub = STUB_LENGTHS[i % 2]
        ex_, ey, lrot = pin_exit(float(p["x"]), float(p["y"]), float(p.get("rot") or 0), stub)
        wires.append({"pin": f"{ref}.{pin}", "from": [p["x"], p["y"]], "to": [ex_, ey]})
        labels.append({"pin": f"{ref}.{pin}", "at": [ex_, ey], "rotation": lrot, "net": net})
    return {"net": net, "wires": wires, "labels": labels, "skipped": skipped, "errors": errors, "ok": not errors}


def wiring_js(plan: Dict[str, Any], label_size: int = 7) -> str:
    """JavaScript that creates the planned stub wires and net labels (signatures from desk/draw.py)."""
    stmts = []
    for w, l in zip(plan["wires"], plan["labels"]):
        x, y = w["from"]; ex_, ey = w["to"]
        stmts.append(f"await eda.sch_PrimitiveWire.create([{x},{y},{ex_},{ey}],{json.dumps(plan['net'])});")
        stmts.append(f"{{const L=await eda.sch_PrimitiveAttribute.createNetLabel({ex_},{ey},{json.dumps(plan['net'])});"
                     f" try{{await eda.sch_PrimitiveAttribute.modify(L.getState_PrimitiveId(),{{rotation:{l['rotation']},fontSize:{label_size}}});}}catch(e){{}}}}")
    return "\n".join(stmts) + f"\nreturn {{wired:{len(plan['wires'])}}};"


# ----------------------------------------------------------------------------- live helpers
def read_schematic(project_path: str, window_id: Optional[str] = None, save: bool = True) -> Dict[str, Any]:
    """Read-only: components, pins with absolute coordinates, nets. Writes state/sch_dump.json when save."""
    from desk.bridge import ex, guard, load_project
    P = load_project(project_path)
    js = guard(P["sheet_uuid"], open_doc=False) + READ_JS
    data = ex(js, timeout=120, retries=0, window_id=window_id or P.get("window_id"), project_path=project_path, is_mutation=False)
    if not isinstance(data, dict) or "parts" not in data:
        raise RuntimeError(f"schematic readback returned {type(data).__name__}: {str(data)[:200]}")
    out = {"project": project_path, "sheet_uuid": P["sheet_uuid"], "parts": data["parts"], "netlist_ok": data.get("netlist_ok"),
           "part_count": len(data["parts"]), "pin_count": sum(len(p.get("pins", [])) for p in data["parts"]),
           "nets": sorted({p["net"] for part in data["parts"] for p in part.get("pins", []) if p.get("net")})}
    if save:
        atomic_write_json(os.path.join(project_path, "state", "sch_dump.json"), out, indent=1)
    return out


def wire_net(project_path: str, net: str, pin_refs: List[str], window_id: Optional[str] = None,
             apply: bool = False, dump: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Plan (and with apply=True, execute under the single-writer lock) DESK-style wiring of `pin_refs` to `net`."""
    dump = dump or read_schematic(project_path, window_id, save=True)
    plan = plan_net_wires(dump, net, pin_refs)
    plan["applied"] = False
    if not apply or not plan["ok"] or not plan["wires"]:
        return plan
    from desk import ops
    from desk.bridge import ex, guard, load_project
    P = load_project(project_path)
    with ops.write_op(project_path, "wire_net", net) as rec:
        rec["dirty"] = True
        res = ex(guard(P["sheet_uuid"], open_doc=False) + wiring_js(plan), timeout=120, retries=0,
                 window_id=window_id or P.get("window_id"), project_path=project_path, is_mutation=True)
        rec["dirty"] = False
    plan["applied"] = True
    plan["result"] = res
    # read back: the pins must now report the net
    after = read_schematic(project_path, window_id, save=True)
    plan["verified_pins"] = [w["pin"] for w in plan["wires"] if (find_pin(after, *parse_pin_ref(w["pin"])) or {}).get("net") == net]
    plan["unverified_pins"] = [w["pin"] for w in plan["wires"] if w["pin"] not in plan["verified_pins"]]
    return plan
