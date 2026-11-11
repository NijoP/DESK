"""Read-only schematic readback: components, pins with absolute coordinates and nets -> state/sch_dump.json (no mutation).
  python tools/sch_dump.py projects/<P> [--window <id>] [--json]
"""
import json
import os
import sys

from _common import S  # noqa: F401


def main(argv):
    if not argv or argv[0].startswith("-"):
        raise SystemExit(__doc__)
    proj = argv[0]
    win = argv[argv.index("--window") + 1] if "--window" in argv else None
    from desk.schematic_io import read_schematic
    d = read_schematic(proj, win, save=True)
    if "--json" in argv:
        print(json.dumps({k: v for k, v in d.items() if k != "netlist"}, indent=1))
    else:
        print(f"sheet {d['sheet_uuid']}: {d['part_count']} parts, {d['pin_count']} pins, {len(d['nets'])} nets"
              f" -> {os.path.join(proj, 'state', 'sch_dump.json')}")
        for part in d["parts"]:
            wired = sum(1 for p in part["pins"] if p.get("net"))
            print(f"  {part['ref']:8s} {str(part.get('dev') or ''):28s} ({part['x']},{part['y']}) pins {len(part['pins'])} on-net {wired}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
