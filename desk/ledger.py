"""Project ledger: the durable memory of a product. projects/<P>/LEDGER.jsonl (committed to git, append-only).

One JSON object per line:
  {"id":"L-0007","ts":"2026-01-05T10:22:00","type":"decision","text":"...","block":"02_PWR_3V3",
   "source":"TPS62840 datasheet p.12","spec_hash":"9f1c..."}
Types:
  decision    a choice + reason (human or model, must have a source or rationale)
  fact        a verified external fact (datasheet value, client confirmation) with source
  assumption  a PROVISIONAL working assumption + risk
  correction  something changed vs an earlier entry (refs: the corrected id)
  built       written by tools/build.py
  verified    written by tools/verify.py (carries spec_hash -> becomes STALE when the block spec changes)
Entries are never edited; supersede them with a 'correction' entry (field 'refs')."""
import json, os, hashlib, datetime

TYPES = ("decision", "fact", "assumption", "correction", "built", "verified", "release",
         "placement_freeze", "routing_attempt", "drc_convergence", "readiness")


def path(project):
    return os.path.join(project, "LEDGER.jsonl")


_LEDGER_CACHE = {}  # path -> (mtime, size, entries)

def read(project):
    p = path(project)
    if not os.path.exists(p):
        return []
    try:
        st = os.stat(p)
        cached = _LEDGER_CACHE.get(p)
        if cached and cached[0] == st.st_mtime and cached[1] == st.st_size:
            return list(cached[2])
        with open(p, encoding="utf-8") as f:
            entries = [json.loads(ln) for ln in f if ln.strip()]
        _LEDGER_CACHE[p] = (st.st_mtime, st.st_size, entries)
        return entries
    except Exception:
        with open(p, encoding="utf-8") as f:
            return [json.loads(ln) for ln in f if ln.strip()]


def block_hash(block, lib=None):
    """Hash of the electrically relevant content of a block (status / bookkeeping excluded).
    With lib (library/devices.json) the resolved device of every MPN is included, so re-resolving a part to a
    different library symbol also invalidates earlier verifications."""
    core = {k: v for k, v in block.items() if k not in ("status", "_file")}
    if lib is not None:
        core["_devices"] = {m: [lib.get(m, {}).get("libraryUuid"), lib.get(m, {}).get("uuid")]
                            for m in sorted({p.get("mpn") for p in block.get("parts", []) if p.get("mpn")})}
    return hashlib.sha1(json.dumps(core, sort_keys=True).encode()).hexdigest()[:12]


def _count_entries(project):
    p = path(project)
    if not os.path.exists(p): return 0
    cached = _LEDGER_CACHE.get(p)
    if cached: return len(cached[2])
    with open(p, "rb") as f:
        return sum(1 for ln in f if ln.strip())

def add(project, type_, text, block=None, source=None, spec_hash=None, refs=None):
    if type_ not in TYPES:
        raise SystemExit(f"ledger type must be one of {TYPES}")
    if type_ in ("decision", "fact", "assumption") and not source:
        raise SystemExit(f"a ledger '{type_}' needs --source (datasheet page, client mail, calculation, ...)")
    n_entries = _count_entries(project)
    e = {"id": f"L-{n_entries + 1:04d}", "ts": datetime.datetime.now().isoformat(timespec="seconds"),
         "type": type_, "text": text}
    for k, v in (("block", block), ("source", source), ("spec_hash", spec_hash), ("refs", refs)):
        if v:
            e[k] = v
    p = path(project)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(e, ensure_ascii=False) + "\n")
    # Invalidate or update cache
    if p in _LEDGER_CACHE:
        try:
            st = os.stat(p)
            _LEDGER_CACHE[p][2].append(e)
            _LEDGER_CACHE[p] = (st.st_mtime, st.st_size, _LEDGER_CACHE[p][2])
        except Exception:
            _LEDGER_CACHE.pop(p, None)
    return e


def superseded(entries):
    return {r for e in entries if e["type"] == "correction" for r in ([e["refs"]] if isinstance(e.get("refs"), str) else e.get("refs") or [])}


def verification_state(entries, block_id, current_hash):
    """'fresh' | 'stale' | 'never' for the latest 'verified' entry of a block."""
    v = [e for e in entries if e["type"] == "verified" and e.get("block") == block_id]
    if not v:
        return "never"
    return "fresh" if v[-1].get("spec_hash") == current_hash else "stale"
