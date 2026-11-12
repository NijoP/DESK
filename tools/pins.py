"""Dump the real symbol pins (number + name) of library devices into library/pins/<MPN>.json.
Write the block 'pins' map from THIS output, never from memory or the datasheet alone.
Usage: python tools/pins.py projects/<P>                        all MPNs of the project without a pin cache
       python tools/pins.py projects/<P> --mpn TPS62840DLCR ...  specific MPNs, probed on THAT project's sheet
       add --force to re-probe cached MPNs
The part is placed far off-sheet on the project's bound schematic window and deleted again: a short live
mutation, journaled under the single-writer lock. The window always comes from the named project's
project.json (or EDA_WINDOW_ID); there is no default project."""
import os
import sys

from _common import ex, S, load_project

PROBE_JS = '''const c=await eda.sch_PrimitiveComponent.create({libraryUuid:"%s",uuid:"%s"},-5000,-5000,"",0,false,true,true);
const ps=await eda.sch_PrimitiveComponent.getAllPinsByPrimitiveId(c.getState_PrimitiveId());
const o=ps.map(p=>({num:p.getState_PinNumber(),name:p.getState_PinName()}));
await eda.sch_PrimitiveComponent.delete([c.getState_PrimitiveId()]); return o;'''


def main(argv):
    pos = [a for a in argv if not a.startswith("--")]
    if not pos or pos[0].startswith("-") or not os.path.isdir(pos[0]):
        raise SystemExit(__doc__)
    proj = pos[0]
    P = load_project(proj)
    window_id = os.environ.get("EDA_WINDOW_ID") or P.get("window_id")
    if not window_id:
        raise SystemExit(f"{os.path.join(proj, 'project.json')} has no window_id and EDA_WINDOW_ID is unset; "
                         "bind the EasyEDA window first (python tools/ping.py " + proj + ")")
    from desk import ops
    from desk.fsutil import atomic_write_json
    lib = S.load_library()
    if "--mpn" in argv:
        want = [a for a in argv[argv.index("--mpn") + 1:] if not a.startswith("--")]
    else:
        want = sorted({p["mpn"] for b in S.load_blocks(proj) for p in b["parts"]})
    if not want:
        raise SystemExit("no MPNs to probe")
    os.makedirs(S.PIN_DIR, exist_ok=True)
    rc = 0
    for m in want:
        if m not in lib:
            print(f"SKIP {m}: not resolved (run tools/resolve.py)")
            rc = 1
            continue
        if S.load_pins(m) and "--force" not in argv:
            continue
        d = lib[m]
        with ops.write_op(proj, "pins_probe", m, classification=ops.OP_IDEMPOTENT_MUTATION) as rec:
            rec["dirty"] = True
            r = ex(PROBE_JS % (d["libraryUuid"], d["uuid"]), window_id=window_id, project_path=proj, is_mutation=True)
            rec["dirty"] = False
        if not isinstance(r, list):
            print(f"FAIL {m}: probe returned {str(r)[:120]}")
            rc = 1
            continue
        r.sort(key=lambda q: (len(str(q["num"])), str(q["num"])))
        atomic_write_json(os.path.join(S.PIN_DIR, S.safe(m) + ".json"), r, indent=0)
        print(f"{m}: " + ", ".join(f"{q['num']}={q['name']}" for q in r))
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
