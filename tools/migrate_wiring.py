"""Move an EXISTING project to the `subsystem` wiring style (docs/02_SCHEMATIC_STYLE.md) - explicit, previewed, backed up.

Usage:
  python tools/migrate_wiring.py projects/<P>                  preview: what would be wired, which drawn blocks would
                                                               need a rebuild; writes state/wiring_migration_preview.json
                                                               and changes nothing else
  python tools/migrate_wiring.py projects/<P> --apply TOKEN    backs up project.json to state/backups/, then sets
                                                               "wiring": "subsystem". TOKEN is the preview's token; a
                                                               spec / project change after the preview voids it

Never touches the live sheet, never rebuilds a block. Blocks already drawn keep their labels drawing (tools/verify.py
keeps accepting them) until you rebuild each one yourself: tools/clear_block.py, then tools/build.py.
"""
import datetime
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from desk import spec as S  # noqa: E402
from desk.fsutil import atomic_write_json  # noqa: E402

PREVIEW = os.path.join("state", "wiring_migration_preview.json")


def _layout(project):
    f = os.path.join(project, "state", "layout.json")
    if not os.path.exists(f):
        return {}
    with open(f, encoding="utf-8") as h:
        return json.load(h).get("blocks", {})


def _token(project):
    """Fingerprint of everything the preview was computed from: project.json, every block spec, the layout."""
    h = hashlib.sha256()
    bdir = os.path.join(project, "blocks")
    names = ["project.json"] + sorted("blocks/" + n for n in (os.listdir(bdir) if os.path.isdir(bdir) else [])
                                      if n.endswith(".json")) + ["state/layout.json"]
    for n in names:
        f = os.path.join(project, *n.split("/"))
        h.update(n.encode())
        if os.path.exists(f):
            with open(f, "rb") as fh:
                h.update(fh.read().replace(b"\r\n", b"\n"))
    return h.hexdigest()[:12]


def preview(project, to="subsystem"):
    if to not in S.WIRING_POLICIES:
        raise SystemExit(f"--to must be one of {S.WIRING_POLICIES}")
    pj = S.load_project_json(project)
    blocks = S.load_blocks(project)
    layout = _layout(project)
    out = {"project": os.path.basename(os.path.abspath(project)), "from": pj.get("wiring", S.LEGACY_WIRING), "to": to,
           "blocks": {}, "rebuild_needed": [], "token": _token(project)}
    for b in blocks:
        bid = b["id"]
        try:
            now, after = S.wiring_policy(pj, b), S.wiring_policy(dict(pj, wiring=to), b)
        except ValueError as e:
            raise SystemExit(f"STOP: {e}")
        cls = S.classify_nets(b, blocks, pj.get("rails", []))
        count = {}
        for p in b.get("parts", []):
            for net in p.get("pins", {}).values():
                count[net] = count.get(net, 0) + 1
        wired = sorted(n for n, c in cls.items() if after == "subsystem" and c in ("local", "port", "cross")
                       and count[n] >= 2 and n not in b.get("label_nets", []))
        built = bid in layout
        drawn = (layout.get(bid) or {}).get("wiring", "labels") if built else None
        out["blocks"][bid] = {"policy_now": now, "policy_after": after, "built": built, "drawn_with": drawn,
                              "wired_nets": wired, "labelled_nets": sorted(n for n in cls if n not in wired),
                              "block_override": b.get("wiring")}
        if built and drawn != after:
            out["rebuild_needed"].append(bid)
    atomic_write_json(os.path.join(project, PREVIEW), out, indent=1)
    return out


def apply(project, token, to="subsystem"):
    f = os.path.join(project, PREVIEW)
    if not os.path.exists(f):
        raise SystemExit("STOP: no preview - run python tools/migrate_wiring.py <project> first")
    with open(f, encoding="utf-8") as h:
        prev = json.load(h)
    if token != prev.get("token") or prev.get("to") != to:
        raise SystemExit(f"STOP: token {token} does not match the last preview ({prev.get('token')}, to {prev.get('to')})")
    if _token(project) != token:
        raise SystemExit("STOP: the project changed since the preview - preview again and review it")
    pj_path = os.path.join(project, "project.json")
    with open(pj_path, encoding="utf-8") as h:
        original = h.read()
    pj = json.loads(original)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bdir = os.path.join(project, "state", "backups")
    os.makedirs(bdir, exist_ok=True)
    backup, n = os.path.join(bdir, f"project.json.{stamp}.bak"), 1
    while os.path.exists(backup):
        backup, n = os.path.join(bdir, f"project.json.{stamp}.{n}.bak"), n + 1
    with open(backup, "w", encoding="utf-8", newline="\n") as h:
        h.write(original)
    pj["wiring"] = to
    atomic_write_json(pj_path, pj, indent=1)
    from desk import ledger as LG
    LG.add(project, "decision", f"wiring policy {prev['from']} -> {to} (migration preview {token}); drawn blocks "
           f"{prev['rebuild_needed'] or 'none'} stay as drawn until rebuilt", source=f"tools/migrate_wiring.py {token}")
    return {"backup": backup, "project_json": pj_path, "rebuild_needed": prev["rebuild_needed"]}


def main(argv):
    args = [a for i, a in enumerate(argv) if not a.startswith("--") and (i == 0 or argv[i - 1] not in ("--apply", "--to"))]
    if not args:
        raise SystemExit(__doc__)
    project = args[0]
    to = argv[argv.index("--to") + 1] if "--to" in argv else "subsystem"
    if "--apply" in argv:
        res = apply(project, argv[argv.index("--apply") + 1], to)
        print(f"MIGRATED: project.json now has \"wiring\": \"{to}\"; backup {res['backup']}")
        for bid in res["rebuild_needed"]:
            print(f"  {bid}: still drawn with labels - when ready: python tools/clear_block.py {project} {bid}"
                  f" && python tools/build.py {project} {bid}")
        return
    prev = preview(project, to)
    print(f"PREVIEW (nothing changed) {prev['project']}: wiring {prev['from']} -> {prev['to']}")
    for bid, b in prev["blocks"].items():
        state = f"drawn with {b['drawn_with']}" if b["built"] else "not built"
        print(f"  {bid}: {b['policy_now']} -> {b['policy_after']} ({state}); wires for {b['wired_nets'] or 'no nets'}")
    print(f"  rebuild needed after migrating: {prev['rebuild_needed'] or 'none'} (never done automatically)")
    print(f"APPLY: python tools/migrate_wiring.py {project} --apply {prev['token']}")


if __name__ == "__main__":
    main(sys.argv[1:])
