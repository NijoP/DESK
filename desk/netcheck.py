"""Pure comparison of a live sheet snapshot against the block specs (no EasyEDA here -> unit-testable).
snapshot parts: [{ref, dev, pins:[{num,name,net,nc}]}]  (produced by the live reader in tools/verify.py)"""
import collections


def compare(blocks, check_ids, parts, lib):
    """Return (errors, nets{name:[ref.pin]}, single_pin_nets). check_ids = block ids to compare part-by-part.

    Fail-closed (report F-1): an empty `check_ids` or an id that names no block spec is an error, because comparing
    zero parts proves nothing and must never read as VERIFIED."""
    E = []
    known = {b.get("id") for b in blocks}
    if not check_ids:
        E.append("no block selected for comparison (no state/layout.json and no block id given) - nothing was verified")
    for bid in sorted(set(check_ids or ()) - known):
        E.append(f"block '{bid}' is not in the block specs - nothing was compared for it")
    live = {p["ref"]: p for p in parts}
    spec_nets, spec_refs = collections.Counter(), set()
    for b in blocks:
        for p in b["parts"]:
            spec_refs.add(p["ref"])
            for net in p.get("pins", {}).values(): spec_nets[net] += 1
    for b in blocks:
        if b["id"] not in check_ids: continue
        for p in b["parts"]:
            r, L = p["ref"], live.get(p["ref"])
            if not L: E.append(f"{b['id']}: {r} missing on sheet"); continue
            want = lib.get(p["mpn"], {}).get("name", p["mpn"])
            if L.get("dev") and want and L["dev"] != want: E.append(f"{r}: device {L['dev']} != spec {want}")
            lp = {q["num"]: q for q in L["pins"]}
            for num, net in p.get("pins", {}).items():
                got = lp.get(num, {}).get("net")
                if got != net: E.append(f"{r}.{num}({lp.get(num, {}).get('name')}): net {got} != spec {net}")
            for num in p.get("nc", []):
                if not lp.get(num, {}).get("nc"): E.append(f"{r}.{num}: NC flag missing")
            for num, q in lp.items():
                if num not in p.get("pins", {}) and num not in p.get("nc", []) and q.get("net"):
                    E.append(f"{r}.{num}: on net {q['net']} but not in spec")
    nets = collections.defaultdict(list)
    for p in parts:
        for q in p["pins"]:
            if q.get("net"): nets[q["net"]].append(f"{p['ref']}.{q['num']}")
    for n, ps in nets.items():
        if n not in spec_nets: E.append(f"unexpected net {n} on {ps[:6]} -> label collision or stray wire")
    for r in sorted(set(live) - spec_refs):
        E.append(f"{r}: on sheet but in no block spec")
    singles = sorted(n for n, ps in nets.items() if len(ps) == 1)
    return E, dict(nets), singles
