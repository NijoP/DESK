"""Wire named pins to a net by name (REF.PIN), DESK style: stub wire + net label; dry-run by default, --apply mutates under the writer lock.
  python tools/wire.py projects/<P> <NET> U1.3 C2.1 ...          plan only (reads the live sheet, no mutation)
  python tools/wire.py projects/<P> <NET> U1.3 C2.1 ... --apply  create wires + labels, then read back and verify
"""
import json
import sys

from _common import S  # noqa: F401


def main(argv):
    args = [x for x in argv if not x.startswith("--")]
    if "--window" in argv:
        args = [x for x in args if x != argv[argv.index("--window") + 1]]
    if len(args) < 3:
        raise SystemExit(__doc__)
    proj, net, pins = args[0], args[1], args[2:]
    win = argv[argv.index("--window") + 1] if "--window" in argv else None
    from desk.schematic_io import wire_net
    plan = wire_net(proj, net, pins, win, apply="--apply" in argv)
    if "--json" in argv:
        print(json.dumps(plan, indent=1))
    else:
        for w in plan["wires"]:
            print(f"  {w['pin']:10s} wire {w['from']} -> {w['to']}  label {net}")
        for s in plan["skipped"]:
            print("  skip:", s)
        for e in plan["errors"]:
            print("  ERROR:", e)
        if plan.get("applied"):
            print(f"applied: verified {plan['verified_pins']} unverified {plan['unverified_pins']}")
        else:
            print("dry run (add --apply to create)" if plan["ok"] else "refused: fix the errors above")
    return 0 if plan["ok"] and not plan.get("unverified_pins") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
