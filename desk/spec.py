"""Block spec loading + offline lint. No EasyEDA needed. This is the gate a model must pass BEFORE drawing.

Block spec = projects/<product>/blocks/NN_<ID>.json  (see templates/block.template.json)
Shared device library = library/devices.json  {MPN: {libraryUuid, uuid, name, footprint, lcsc}}
Pin cache           = library/pins/<MPN>.json  [{num, name}]  (made by tools/pins.py)
"""
import json, os, glob, re, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB_FILE = os.path.join(ROOT, "library", "devices.json")
PIN_DIR = os.path.join(ROOT, "library", "pins")
NET_RE = re.compile(r"^[A-Z0-9+_\-./]+$")
POWER_RE = re.compile(r"^(GND|AGND|PGND|\+?\d+V\d*|\+?\d*V\d+.*|VBAT.*|VSYS|VBUS|VIN.*|.*_GND)$")


def safe(mpn):
    return re.sub(r"[^A-Za-z0-9._-]", "_", mpn)


def load_library():
    return json.load(open(LIB_FILE, encoding="utf-8")) if os.path.exists(LIB_FILE) else {}


def save_library(lib):
    os.makedirs(os.path.dirname(LIB_FILE), exist_ok=True)
    json.dump(dict(sorted(lib.items())), open(LIB_FILE, "w", encoding="utf-8"), indent=1)


def load_pins(mpn):
    f = os.path.join(PIN_DIR, safe(mpn) + ".json")
    return json.load(open(f, encoding="utf-8")) if os.path.exists(f) else None


def load_blocks(project):
    files = sorted(glob.glob(os.path.join(project, "blocks", "*.json")))
    blocks = []
    for f in files:
        b = json.load(open(f, encoding="utf-8"))
        b["_file"] = os.path.basename(f)
        blocks.append(b)
    return blocks


def find_block(project, key):
    for b in load_blocks(project):
        if key in (b["id"], b["_file"], b["_file"][:-5], b["_file"].split("_")[0]):
            return b
    raise SystemExit(f"block '{key}' not found in {project}/blocks")


def lint(project, only=None, final=False):
    """Return (errors, warnings). final=True also requires every net to have >=2 pins project-wide."""
    E, W = [], []
    lib = load_library()
    blocks = load_blocks(project)
    refs = collections.Counter()
    net_pins = collections.defaultdict(list)        # project-wide
    for b in blocks:
        for k in ("id", "title", "parts"):
            if k not in b: E.append(f"{b['_file']}: missing key '{k}'")
        for p in b.get("parts", []):
            refs[p["ref"]] += 1
            for num, net in p.get("pins", {}).items():
                net_pins[net].append((b["id"], p["ref"], num))
    for r, n in refs.items():
        if n > 1: E.append(f"designator {r} used {n} times")
    for b in blocks:
        if only and b["id"] != only: continue
        tag = b["id"]
        ports = set(b.get("ports", []))
        local = collections.defaultdict(list)
        for p in b.get("parts", []):
            ref, mpn = p.get("ref"), p.get("mpn")
            if not re.match(r"^[A-Z]+\d+$", ref or ""): E.append(f"{tag}: bad ref '{ref}' (use R12, U3, FPC1 ...)")
            if not mpn: E.append(f"{tag}/{ref}: no mpn"); continue
            if mpn not in lib: E.append(f"{tag}/{ref}: {mpn} not in library/devices.json -> run tools/resolve.py")
            pins = load_pins(mpn)
            mapped = set(p.get("pins", {})) | set(p.get("nc", []))
            if pins is None:
                (E if final else W).append(f"{tag}/{ref}: no pin cache for {mpn} -> run tools/pins.py {mpn}")
            else:
                nums = {q["num"] for q in pins}
                for n in mapped - nums: E.append(f"{tag}/{ref}: pin '{n}' does not exist on {mpn} (pins: {sorted(nums)})")
                for n in nums - mapped:
                    nm = next(q["name"] for q in pins if q["num"] == n)
                    E.append(f"{tag}/{ref}: pin {n} ({nm}) is neither connected nor in 'nc' -> every pin must be decided")
            both = set(p.get("pins", {})) & set(p.get("nc", []))
            for n in both: E.append(f"{tag}/{ref}: pin {n} is both connected and NC")
            for num, net in p.get("pins", {}).items():
                if not NET_RE.match(net): E.append(f"{tag}/{ref}.{num}: net '{net}' - use UPPER_CASE, no spaces")
                local[net].append(ref)
        for net, rs in local.items():
            if len(rs) == 1 and net not in ports and not POWER_RE.match(net):
                E.append(f"{tag}: net {net} touches only {rs[0]} and is not a declared port -> missing connection or add to 'ports'")
        for port in ports:
            if port not in local: W.append(f"{tag}: port {port} declared but not used in block")
        for q in b.get("qa", []):
            if q.get("pass") is not True: E.append(f"{tag}: QA item '{q.get('item')}' not passed")
        if not b.get("qa") and any(p["ref"][0] == "U" for p in b.get("parts", [])):
            W.append(f"{tag}: block has ICs but no 'qa' entries (datasheet values unchecked)")
    if final:
        for net, ps in net_pins.items():
            if len(ps) == 1: E.append(f"net {net} has a single pin project-wide: {ps[0]}")
    return E, W
