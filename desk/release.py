"""Manufacturing release checks (pure functions; tools/release.py does the live export).
A release is accepted only if every gate below passes; the manifest records file hashes + gate evidence."""
import csv, hashlib, io, json, os, re, zipfile


def spec_refs(blocks, include_dni=False):
    return {p["ref"] for b in blocks for p in b["parts"] if include_dni or not p.get("dni")}


def _expand(field):
    """'C1,C2 C5-C7' -> {C1,C2,C5,C6,C7}"""
    out = set()
    for tok in re.split(r"[,\s;]+", field or ""):
        m = re.match(r"^([A-Z]+)(\d+)-(?:[A-Z]+)?(\d+)$", tok)
        if m:
            out |= {f"{m.group(1)}{i}" for i in range(int(m.group(2)), int(m.group(3)) + 1)}
        elif tok:
            out.add(tok)
    return out


def _rows(text):
    text = text.lstrip("\ufeff")
    sample = text[:2000]
    delim = "\t" if sample.count("\t") > sample.count(",") else ","
    return list(csv.DictReader(io.StringIO(text), delimiter=delim))


def _col(row, *names):
    for k in row:
        if k and k.strip().lower() in names: return row[k]
    return None


def check_bom(text, refs):
    """EasyEDA BOM csv vs spec designators. Returns errors."""
    got = set()
    rows = _rows(text)
    if not rows: return ["BOM is empty / unparsable"]
    for r in rows:
        got |= _expand(_col(r, "designator", "designators", "reference") or "")
    E = []
    if got - refs: E.append(f"BOM has parts not in specs: {sorted(got - refs)[:20]}")
    if refs - got: E.append(f"spec parts missing from BOM: {sorted(refs - got)[:20]}")
    return E


def check_pnp(text, refs):
    rows = _rows(text)
    if not rows: return ["pick-and-place is empty / unparsable"]
    got = {(_col(r, "designator", "ref", "reference") or "").strip() for r in rows} - {""}
    E = []
    if refs - got: E.append(f"parts missing from pick-and-place: {sorted(refs - got)[:20]}")
    for r in rows:
        for c in ("mid x", "mid y", "center-x(mm)", "center-y(mm)", "x", "y"):
            v = _col(r, c)
            if v is not None and not re.match(r"^-?[\d.]+(mm|mil)?$", v.strip()):
                E.append(f"bad coordinate {c}={v!r} for {_col(r, 'designator')}"); break
    return E


GERBER_NEED = {"copper top": re.compile(r"(\.gtl$|toplayer|top_layer|copper_top|-f_cu)", re.I),
               "copper bottom": re.compile(r"(\.gbl$|bottomlayer|bottom_layer|copper_bottom|-b_cu)", re.I),
               "outline": re.compile(r"(\.gko$|\.gm1$|boardoutline|board_outline|edge_cuts|outline)", re.I),
               "drill": re.compile(r"(\.drl$|\.xln$|drill|\.txt$)", re.I),
               "solder mask": re.compile(r"(\.gts$|\.gbs$|soldermask|solder_mask|mask)", re.I)}


def check_gerber(zip_path, layers=2):
    E = []
    try:
        names = zipfile.ZipFile(zip_path).namelist()
    except zipfile.BadZipFile:
        return ["Gerber file is not a zip"], []
    for what, rx in GERBER_NEED.items():
        if not any(rx.search(n) for n in names): E.append(f"Gerber zip has no {what} file")
    if layers > 2:
        inner = [n for n in names if re.search(r"(inner|\.g\d+$|in\d_cu|\.gp\d$)", n, re.I)]
        if len(inner) < layers - 2: E.append(f"{layers}-layer board but only {len(inner)} inner layer files")
    return E, names


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""): h.update(chunk)
    return h.hexdigest()


def write_manifest(rel_dir, rev, files, gates, extra=None):
    m = {"revision": rev, "files": {os.path.basename(f): {"sha256": sha256(f), "bytes": os.path.getsize(f)} for f in files},
         "gates": gates, **(extra or {})}
    with open(os.path.join(rel_dir, "MANIFEST.json"), "w", encoding="utf-8") as f: json.dump(m, f, indent=1)
    return m


def verify_manifest(rel_dir):
    with open(os.path.join(rel_dir, "MANIFEST.json"), encoding="utf-8") as f: m = json.load(f)
    bad = [n for n, d in m["files"].items() if not os.path.exists(os.path.join(rel_dir, n)) or sha256(os.path.join(rel_dir, n)) != d["sha256"]]
    return bad
