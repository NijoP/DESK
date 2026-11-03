"""Independent offline electrical rules on the block specs (uses real symbol pin names from library/pins).
These run without EasyEDA and are deliberately conservative: ERROR = almost certainly wrong, WARN = review.
EasyEDA's own ERC (tools/erc.py, live) is the second, independent check."""
import re, collections
from desk import spec as S
from desk.calc import parse_value

GND_NET = re.compile(r"^(A|P|D|S)?GND(_.*)?$|^.*_GND$|^VSS$")
GND_PIN = re.compile(r"^(A|P|D)?GND\d*$|^VSS\d*$|^AVSS$|^DVSS$")
PWR_PIN = re.compile(r"^(VCC|VDD|AVDD|DVDD|VDDIO|VDDA|VIN|PVIN|AVIN|VBUS|VBAT|VCCIO|VDD\d*V\d*)\d*$")
NC_PIN = re.compile(r"^(NC|N\.C\.|DNC)\d*$")
RAIL_V = {"VBUS": 5.5, "USB_VBUS": 5.5, "VBAT": 4.2, "VSYS": 4.5}


def rail_voltage(net):
    if net in RAIL_V: return RAIL_V[net]
    m = re.match(r"^\+?(\d+)V(\d*)", net)
    return float(f"{m.group(1)}.{m.group(2) or 0}") if m else None


def check(project):
    E, W = [], []
    blocks = S.load_blocks(project)
    caps_on = collections.defaultdict(list)          # net -> caps that go from net to ground
    for b in blocks:
        for p in b["parts"]:
            if re.match(r"^C\d", p["ref"]) and len(p.get("pins", {})) == 2:
                a, c = list(p["pins"].values())
                if GND_NET.match(c): caps_on[a].append(p["ref"])
                if GND_NET.match(a): caps_on[c].append(p["ref"])
    for b in blocks:
        for p in b["parts"]:
            ref, pins = p["ref"], S.load_pins(p.get("mpn", "")) or []
            name = {q["num"]: q["name"].strip().upper() for q in pins}
            for num, net in p.get("pins", {}).items():
                nm = name.get(num, "")
                if GND_PIN.match(nm) and not GND_NET.match(net):
                    E.append(f"{b['id']}/{ref}.{num} ({nm}) is a ground pin but on net {net}")
                if PWR_PIN.match(nm):
                    if GND_NET.match(net): E.append(f"{b['id']}/{ref}.{num} ({nm}) supply pin tied to ground net {net}")
                    elif not caps_on.get(net): W.append(f"{b['id']}/{ref}.{num} ({nm}) on {net}: no capacitor from {net} to ground anywhere")
                if NC_PIN.match(nm): W.append(f"{b['id']}/{ref}.{num} is '{nm}' in the symbol but connected to {net}")
            if ref.startswith("C") and p.get("rating"):
                m = re.search(r"(\d+(?:\.\d+)?)\s*V", p["rating"])
                vmax = max([v for v in (rail_voltage(n) for n in p.get("pins", {}).values()) if v] or [0])
                if m and vmax and float(m.group(1)) < vmax:
                    E.append(f"{b['id']}/{ref}: rated {m.group(1)} V on a {vmax} V rail (over-voltage)")
                elif m and vmax and float(m.group(1)) < 1.5 * vmax:
                    W.append(f"{b['id']}/{ref}: rated {m.group(1)} V on {vmax} V (< 1.5x, check DC-bias derating)")
            if ref.startswith("R") and p.get("value") and parse_value(p["value"]) is None:
                W.append(f"{b['id']}/{ref}: value '{p['value']}' is not numeric (use 10k, 4k7, 2R2)")
    return E, W
