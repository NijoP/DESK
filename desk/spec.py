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
    if not os.path.exists(LIB_FILE): return {}
    with open(LIB_FILE, encoding="utf-8") as f: return json.load(f)


def save_library(lib):
    os.makedirs(os.path.dirname(LIB_FILE), exist_ok=True)
    with open(LIB_FILE, "w", encoding="utf-8") as f: json.dump(dict(sorted(lib.items())), f, indent=1)


def load_pins(mpn):
    f = os.path.join(PIN_DIR, safe(mpn) + ".json")
    if not os.path.exists(f): return None
    with open(f, encoding="utf-8") as fh: return json.load(fh)


def load_blocks(project):
    files = sorted(glob.glob(os.path.join(project, "blocks", "*.json")))
    blocks = []
    for f in files:
        with open(f, encoding="utf-8") as fh:
            b = json.load(fh)
        b["_file"] = os.path.basename(f)
        blocks.append(b)
    return blocks


def _block_matches(b, key):
    """A block is named by its id, file name, file stem or numeric file prefix ('02' for 02_PWR.json)."""
    return key in (b.get("id"), b["_file"], b["_file"][:-5], b["_file"].split("_")[0])


def resolve_block_id(blocks, key):
    """Canonical block id for `key` (id or one of its aliases), or None when no block matches."""
    for b in blocks:
        if _block_matches(b, key):
            return b.get("id")
    return None


def find_block(project, key):
    for b in load_blocks(project):
        if _block_matches(b, key):
            return b
    raise SystemExit(f"block '{key}' not found in {project}/blocks")


# ------------------------------------------------------------------ wiring policy, net classes, sheets (docs/02)
WIRING_POLICIES = ("subsystem", "labels")
LEGACY_WIRING = "labels"            # a project.json without "wiring" keeps today's style: never rewritten silently
NEW_PROJECT_WIRING = "subsystem"    # templates/project/project.json, so every new project is physically wired
NET_CLASSES = ("power", "port", "cross", "local", "single")


def load_project_json(project):
    f = os.path.join(project, "project.json")
    if not os.path.exists(f): return {}
    with open(f, encoding="utf-8") as fh: return json.load(fh)


def wiring_policy(project_json, block=None):
    """The wiring style for one block: block 'wiring' (a client requirement for that block) > project.json 'wiring'
    > 'labels' (legacy). An unknown value is an error, never a silent default."""
    for src, val in (("block", (block or {}).get("wiring")), ("project.json", (project_json or {}).get("wiring"))):
        if val is not None:
            if val not in WIRING_POLICIES:
                raise ValueError(f"{src} wiring '{val}' is not one of {WIRING_POLICIES}")
            return val
    return LEGACY_WIRING


def is_power(net, rails=()):
    return bool(POWER_RE.match(net)) or net in set(rails or ())


def classify_nets(block, blocks=(), rails=()):
    """{net: class} for every net of `block`, from the spec alone:
    power  - rail / ground (POWER_RE or project.json 'rails'): labels / power-symbol style on every pin
    port   - declared in the block's 'ports': wired inside the block + one interface label
    cross  - also used by another block but not declared a port: wired + one label
    local  - >= 2 pins, only in this block: physical wires, no label needed
    single - one pin, not a port (lint reports it)"""
    ports = set(block.get("ports", []))
    elsewhere = set()
    for b in blocks:
        if b.get("id") == block.get("id"): continue
        for p in b.get("parts", []): elsewhere.update(p.get("pins", {}).values())
    count = collections.Counter(net for p in block.get("parts", []) for net in p.get("pins", {}).values())
    out = {}
    for net in sorted(count):
        if is_power(net, rails): out[net] = "power"
        elif net in ports: out[net] = "port"
        elif net in elsewhere: out[net] = "cross"
        elif count[net] >= 2: out[net] = "local"
        else: out[net] = "single"
    return out


def sheet_of(project_json, block_id):
    """The sheet record ({id, title, uuid?, blocks}) that holds `block_id`, or None for a single-sheet project."""
    for s in (project_json or {}).get("sheets", []) or []:
        if block_id in s.get("blocks", []): return s
    return None


def sheet_uuid_for(project_json, block_ids):
    """The schematic page uuid the given blocks are drawn on. Single-sheet projects: project.json 'sheet_uuid'.
    Multi-sheet: the blocks' sheet 'uuid'; blocks on different sheets, or a sheet with no uuid yet, are an error
    (DESK does not create pages: eda.dmt_Schematic.createSchematicPage is UNVERIFIED-LIVE)."""
    if not (project_json or {}).get("sheets"):
        return project_json["sheet_uuid"]
    block_ids = list(block_ids)
    missing = sorted(b for b in block_ids if sheet_of(project_json, b) is None)
    if missing:
        raise ValueError(f"block(s) {missing} are on no sheet in project.json 'sheets'")
    sheets = sorted({sheet_of(project_json, b)["id"] for b in block_ids})
    if len(sheets) != 1:
        raise ValueError(f"blocks {sorted(block_ids)} are on different sheets {sheets}: run one sheet at a time")
    s = sheet_of(project_json, block_ids[0])
    if not s.get("uuid"):
        raise ValueError(f"sheet '{s['id']}' has no 'uuid': create the page in EasyEDA, then paste its uuid "
                         "(automatic page creation is UNVERIFIED-LIVE)")
    return s["uuid"]


def cross_sheet_ports(project_json, blocks, rails=()):
    """{net: [sheet ids]} for every non-power net used on two or more sheets: the hierarchical / cross-sheet ports."""
    seen = collections.defaultdict(set)
    for b in blocks:
        s = sheet_of(project_json, b.get("id"))
        if s is None: continue
        for p in b.get("parts", []):
            for net in p.get("pins", {}).values():
                if not is_power(net, rails): seen[net].add(s["id"])
    return {n: sorted(v) for n, v in sorted(seen.items()) if len(v) > 1}


def lint_project_model(project_json, blocks):
    """Errors / warnings for the wiring policy and the multi-sheet model of project.json (docs/02)."""
    E, W = [], []
    for src, obj in [("project.json", project_json)] + [(b.get("_file", b.get("id")), b) for b in blocks]:
        v = (obj or {}).get("wiring")
        if v is not None and v not in WIRING_POLICIES:
            E.append(f"{src}: wiring '{v}' is not one of {list(WIRING_POLICIES)}")
    sheets = (project_json or {}).get("sheets") or []
    if sheets:
        ids = {b.get("id") for b in blocks}
        where = collections.defaultdict(list)
        for s in sheets:
            if not s.get("id"): E.append(f"project.json sheets: a sheet has no 'id': {s}")
            for bid in s.get("blocks", []):
                where[bid].append(s.get("id"))
                if bid not in ids: E.append(f"sheet {s.get('id')}: block '{bid}' has no spec in blocks/")
        for bid, ss in sorted(where.items()):
            if len(ss) > 1: E.append(f"block {bid} is on more than one sheet: {ss}")
        for bid in sorted(i for i in ids if i not in where):
            E.append(f"block {bid} is on no sheet (project.json 'sheets' must list every block once)")
        for net, on in cross_sheet_ports(project_json, blocks, project_json.get("rails", [])).items():
            for b in blocks:
                uses = any(net in p.get("pins", {}).values() for p in b.get("parts", []))
                if uses and net not in b.get("ports", []):
                    E.append(f"{b.get('id')}: net {net} crosses sheets {on} but is not in the block's 'ports'")
    return E, W


def lint(project, only=None, final=False):
    """Return (errors, warnings). final=True also requires every net to have >=2 pins project-wide."""
    E, W = [], []
    lib = load_library()
    blocks = load_blocks(project)
    try:
        pe, pw = lint_project_model(load_project_json(project), blocks)
    except (OSError, ValueError) as e:
        pe, pw = [f"project.json: {e}"], []
    E += pe; W += pw
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
    if only:
        # An alias (file name, stem, numeric prefix) lints the block it names; a name that matches no block is an
        # error, never a silent "nothing to lint" PASS (report F-2).
        resolved = resolve_block_id(blocks, only)
        if resolved is None:
            E.append(f"block '{only}' not found in {project}/blocks - nothing was linted")
        only = resolved
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
        from desk.calc import check_qa
        computed = {item: (v, ok, msg) for item, v, ok, msg in check_qa(b)}
        for q in b.get("qa", []):
            if q.get("item") in computed:
                v, ok, msg = computed[q.get("item")]
                if not ok: E.append(f"{tag}: QA computed FAIL: {msg}")
                elif q.get("pass") is False: E.append(f"{tag}: QA '{q.get('item')}' marked pass=false but computes OK: {msg}")
                if not q.get("source"): E.append(f"{tag}: QA '{q.get('item')}' has no datasheet source")
            elif q.get("pass") is not True: E.append(f"{tag}: QA item '{q.get('item')}' not passed")
            elif not q.get("source"): W.append(f"{tag}: QA '{q.get('item')}' has no source")
        if not b.get("qa") and any(p["ref"][0] == "U" for p in b.get("parts", [])):
            W.append(f"{tag}: block has ICs but no 'qa' entries (datasheet values unchecked)")
    from desk import erc
    ee, ew = erc.check(project)
    pick = (lambda m: m.startswith(only + "/")) if only else (lambda m: True)
    E += [f"ERC {m}" for m in ee if pick(m)]; W += [f"ERC {m}" for m in ew if pick(m)]
    if final:
        for net, ps in net_pins.items():
            if len(ps) == 1: E.append(f"net {net} has a single pin project-wide: {ps[0]}")
    return E, W
