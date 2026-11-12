"""Board setup: copper layer count + one rectangular outline (desk/routing/outline.py "R" spec), then read back.
Usage: python tools/pcb_board.py projects/<P> --width <mm> --height <mm> [--layers 2|4|6] [--radius <mm>] [--dry]
Live mutation under desk.ops.write_op with a recorded CLI approval. Refuses if an outline already exists on layer 11
(never replaces or deletes one). Uses only verified calls: pcb_Layer.setTheNumberOfCopperLayers,
pcb_MathPolygon.createPolygon + pcb_PrimitivePolyline.create (INC-20261111-008, run 2b R2-F-007)."""
import json
import sys

from _common import ex, load_project


def _arg(argv, name, default=None, cast=float):
    return cast(argv[argv.index(name) + 1]) if name in argv else default


def main(argv):
    pos = [a for a in argv if not a.startswith("--")]
    if not pos:
        raise SystemExit(__doc__)
    proj = pos[0]
    P = load_project(proj)
    w, h = _arg(argv, "--width"), _arg(argv, "--height")
    if not w or not h:
        raise SystemExit("--width and --height (mm) are required")
    layers = _arg(argv, "--layers", 2, int)
    radius = _arg(argv, "--radius", 0.0)
    from desk.routing.outline import outline_create_js, rect_outline_polygon, OUTLINE_LAYER
    js = outline_create_js(w, h, (0.0, 0.0), radius)
    if "--dry" in argv:
        print(json.dumps({"layers": layers, "outline_R": rect_outline_polygon(w, h, (0.0, 0.0), radius)}))
        return 0
    existing = ex("const l=await eda.pcb_PrimitivePolyline.getAll(); return (l||[]).filter(p=>p.getState_Layer()==%d).length;"
                  % OUTLINE_LAYER, project_path=proj)
    if existing:
        raise SystemExit(f"STOP: {existing} outline primitive(s) already on layer {OUTLINE_LAYER}; not replacing")
    from desk import ops
    aid = ops.cli_approval(proj, "pcb_board_setup", P.get("pcb_uuid", "?"), argv=["tools/pcb_board.py"] + list(argv))
    with ops.write_op(proj, "pcb_board_setup", P.get("pcb_uuid", "?"), classification=ops.OP_NON_IDEMPOTENT_MUTATION,
                      approval=aid) as rec:
        rec["dirty"] = True
        r_layers = ex("return await eda.pcb_Layer.setTheNumberOfCopperLayers(%d);" % layers, project_path=proj, is_mutation=True)
        r_outline = ex(js, project_path=proj, is_mutation=True)
        rec["dirty"] = False
    back = ex("""const n=await eda.pcb_Layer.getTheNumberOfCopperLayers();
const l=(await eda.pcb_PrimitivePolyline.getAll()||[]).filter(p=>p.getState_Layer()==%d);
return {copper_layers:n, outlines:l.length, polygon: l.length? l[0].getState_Polygon().polygon : null};""" % OUTLINE_LAYER, project_path=proj)
    ok = back.get("copper_layers") == layers and back.get("outlines") == 1
    print(json.dumps({"set_layers": r_layers, "outline_id": r_outline, "readback": back, "result": "VERIFIED" if ok else "FAIL"}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
