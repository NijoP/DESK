"""DESK Context Engine — give a model exactly what the current task needs, nothing more.

Why it exists: DESK projects grow (docs, requirements, BOM study, block specs with full pin maps, pin caches,
ledger). Reading files whole wastes tokens and buries the facts that matter. The engine builds a small
structural index of the repo + one product and assembles TASK PACKS under a token budget.

Design choices
- Structural first, text search second. DESK data is already structured (block JSON, ID'd requirement rows,
  headed markdown). Relations (block -> requirements, ports -> neighbour blocks, MPN -> pins, block -> ledger)
  are exact, so retrieval for engineering tasks is deterministic. BM25 (`find`) only covers free-text questions.
- Facts are computed, not remembered: every block pack runs the offline lint live and derives the next gate from
  the real state (library, pin cache, layout, ledger), not from the `status` field a model may have mis-set.
- Verified knowledge is preserved in LEDGER.jsonl with sources; verifications carry the block spec hash and are
  shown STALE as soon as the spec changes.
- Incremental: chunks are cached per file content hash (state/ctx_index.json); `delta` serves only what changed
  since the previous pack (state/ctx_served.json).
- Zero dependencies, pure stdlib. Token estimate = chars / 4 (good enough for budgeting).
"""
import json, os, re, glob, math, hashlib, collections

from desk import spec as S
from desk import ledger as LG

ROOT = S.ROOT
# learning/ holds live-verified EasyEDA gotchas (incidents, lessons); indexing them lets
# `ctx.py find` surface a known failure at the moment an agent hits it (roadmap SW-10).
DOC_FILES = ["AGENTS.md", "docs/*.md", "learning/incidents/*.md", "learning/lessons/*.md"]
PROJECT_MD = ["REQUIREMENTS.md", "BOM_SELECTION.md", "BLOCK_PLAN.md", "RESULT.md", "ROUTING_PLAN.md"]
TOK = 4  # chars per token (estimate)
FORMAT = 4  # bump when chunk format changes -> old caches are rebuilt



def _rel(path: str, start: str = None) -> str:
    """Relative path with forward slashes for display in commands; falls back to the absolute path when
    `path` is on another drive than the current directory (os.path.relpath raises ValueError on Windows)."""
    try:
        return os.path.relpath(path, start or os.getcwd()).replace("\\", "/")
    except ValueError:
        return os.path.abspath(path).replace("\\", "/")

def _json(path, default=None):
    if not os.path.exists(path): return default
    with open(path, encoding="utf-8") as f: return json.load(f)


def _dump(obj, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f: json.dump(obj, f)


def tokens(text):
    return (len(text) + TOK - 1) // TOK


def _sha(data):
    return hashlib.sha1(data).hexdigest()[:12]


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


# ----------------------------------------------------------------------------- chunking
def md_sections(text, src):
    """Split markdown into sections at ##/### headings. Text before the first heading is the 'intro'."""
    out, title, buf, level = [], "intro", [], 1
    for ln in text.splitlines():
        m = re.match(r"^(#{1,3})\s+(.*)", ln)
        if m and len(m.group(1)) >= 2:
            if "".join(buf).strip():
                out.append((title, level, "\n".join(buf).strip()))
            title, level, buf = m.group(2).strip(), len(m.group(1)), []
        else:
            buf.append(ln)
    if "".join(buf).strip():
        out.append((title, level, "\n".join(buf).strip()))
    return [{"id": f"{src}#{slug(t)}", "kind": "doc", "title": t, "src": f"{src}#{slug(t)}", "text": body,
             "refs": sorted(set(re.findall(r"\bR-\d+\b", body)))} for t, level, body in out]


def req_rows(text, src):
    """Requirement rows `| R-01 | ... |` -> one chunk per requirement (exact lookup by ID)."""
    out = []
    for i, ln in enumerate(text.splitlines(), 1):
        m = re.match(r"^\|\s*(R-\d+)\s*\|(.*)\|\s*$", ln)
        if m:
            cells = [c.strip() for c in m.group(2).split("|")]
            out.append({"id": f"req:{m.group(1)}", "kind": "req", "title": m.group(1), "src": f"{src}:{i}",
                        "text": f"{m.group(1)} | " + " | ".join(c for c in cells if c), "refs": [m.group(1)],
                        "status": next((c for c in cells if c.upper() in ("CONFIRMED", "PROVISIONAL", "TBD")), "")})
    return out


def block_chunk(b, src):
    return {"id": f"block:{b['id']}", "kind": "block", "title": f"{b['id']} {b.get('title', '')}", "src": src,
            "text": render_block(b, pins=False), "refs": [b["id"]] + b.get("requirements", []),
            "hash": LG.block_hash(b)}


def render_block(b, pins=True, lib=None):
    """Compact, lossless-for-electrics rendering of a block spec (~40 % of the JSON size)."""
    L = [f"[{b['id']}] \"{b.get('title', '')}\" status={b.get('status', '?')}"
         + (f" req={','.join(b['requirements'])}" if b.get("requirements") else "")]
    if b.get("purpose"): L.append(f"purpose: {b['purpose']}")
    L.append("ports: " + " ".join(b.get("ports", [])))
    for p in b.get("parts", []):
        attrs = " ".join(x for x in (p.get("mpn"), p.get("value"), p.get("rating"), p.get("package"),
                                     ("lcsc=" + p["lcsc"]) if p.get("lcsc") else "") if x)
        line = f"{p['ref']} {attrs}"
        if pins:
            line += " | " + " ".join(f"{k}:{v}" for k, v in sorted(p.get("pins", {}).items(), key=lambda kv: _pinkey(kv[0])))
            if p.get("nc"): line += " nc:" + ",".join(p["nc"])
        if p.get("role"): line += f"  -- {p['role']}"
        L.append(line)
    qa = b.get("qa", [])
    if qa:
        L.append(f"qa {sum(1 for q in qa if q.get('pass') is True)}/{len(qa)} pass: "
                 + "; ".join(f"{q.get('item')}={q.get('result')} [{q.get('limit')}] ({q.get('source', 'no source')})"
                             + ("" if q.get("pass") is True else " FAIL") for q in qa))
    for d in b.get("decisions", []): L.append(f"decision: {d}")
    return "\n".join(L)


def _pinkey(n):
    return (0, int(n)) if n.isdigit() else (1, n)


# ----------------------------------------------------------------------------- index
class Index:
    """Incremental chunk index of DESK docs + one product. Rebuilds only files whose content hash changed."""

    def __init__(self, project):
        self.project = os.path.abspath(project)
        self.cache_file = os.path.join(self.project, "state", "ctx_index.json")
        self.stats = {"reused": 0, "parsed": 0, "removed": 0}
        self.files = {}
        self._load()

    def _sources(self):
        src = []
        for pat in DOC_FILES:
            src += [(f, os.path.relpath(f, ROOT).replace("\\", "/")) for f in sorted(glob.glob(os.path.join(ROOT, pat)))]
        for name in PROJECT_MD:
            f = os.path.join(self.project, name)
            if os.path.exists(f): src.append((f, "project/" + name))
        for f in sorted(glob.glob(os.path.join(self.project, "blocks", "*.json"))):
            src.append((f, "project/blocks/" + os.path.basename(f)))
        if os.path.exists(LG.path(self.project)): src.append((LG.path(self.project), "project/LEDGER.jsonl"))
        return src

    def _parse(self, path, rel, raw):
        text = raw.decode("utf-8", errors="replace")
        if rel.endswith(".json"):
            b = json.loads(text); b["_file"] = os.path.basename(path)
            return [block_chunk(b, rel)]
        if rel.endswith("LEDGER.jsonl"):
            out = []
            for ln in text.splitlines():
                if not ln.strip(): continue
                e = json.loads(ln)
                out.append({"id": f"ledger:{e['id']}", "kind": "ledger", "title": e["id"], "src": f"{rel}#{e['id']}",
                            "text": fmt_ledger(e), "refs": [x for x in (e.get("block"),) if x]})
            return out
        chunks = md_sections(text, rel)
        if rel.endswith("REQUIREMENTS.md"): chunks += req_rows(text, rel)
        return chunks

    def _load(self):
        cache = _json(self.cache_file, {})
        old = cache.get("files", {}) if cache.get("format") == FORMAT else {}
        seen = set()
        for path, rel in self._sources():
            with open(path, "rb") as f: raw = f.read()
            h = _sha(raw); seen.add(rel)
            if rel in old and old[rel]["hash"] == h:
                self.files[rel] = old[rel]; self.stats["reused"] += 1
            else:
                self.files[rel] = {"hash": h, "chunks": self._parse(path, rel, raw)}; self.stats["parsed"] += 1
        self.stats["removed"] = len(set(old) - seen)
        if self.stats["parsed"] or self.stats["removed"]:
            _dump({"format": FORMAT, "files": self.files}, self.cache_file)

    def chunks(self, kind=None):
        for f in self.files.values():
            for c in f["chunks"]:
                if kind is None or c["kind"] == kind:
                    yield c

    def get(self, cid):
        return next((c for c in self.chunks() if c["id"] == cid), None)

    def doc(self, file_prefix, title_prefix):
        for c in self.chunks("doc"):
            if c["src"].startswith(file_prefix) and c["title"].lower().startswith(title_prefix.lower()):
                return c
        return None

    # --- BM25 over all chunks (free-text questions only)
    def find(self, query, k=6, kinds=None):
        docs = [c for c in self.chunks() if not kinds or c["kind"] in kinds]
        tok = lambda s: re.findall(r"[a-z0-9+_.\-]+", s.lower())
        q = [t for t in tok(query) if len(t) > 1]
        if not q or not docs: return []
        tfs = [collections.Counter(tok(c["title"] + " " + c["title"] + " " + c["text"])) for c in docs]
        avg = sum(sum(t.values()) for t in tfs) / len(tfs)
        df = collections.Counter(t for tf in tfs for t in set(tf))
        N, k1, bb = len(docs), 1.4, 0.75
        scored = []
        for c, tf in zip(docs, tfs):
            dl = sum(tf.values()); s = 0.0
            for t in q:
                if tf[t]:
                    idf = math.log(1 + (N - df[t] + 0.5) / (df[t] + 0.5))
                    s += idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - bb + bb * dl / avg))
            if s > 0: scored.append((s, c))
        scored.sort(key=lambda x: -x[0])
        return scored[:k]


def fmt_ledger(e, state=None):
    tail = " ".join(x for x in (f"block={e['block']}" if e.get("block") else "", f"src: {e['source']}" if e.get("source") else "",
                                f"refs={e['refs']}" if e.get("refs") else "") if x)
    return f"{e['id']} [{e['type']}{'/' + state if state else ''}] {e['text']}" + (f"  ({tail})" if tail else "")


# ----------------------------------------------------------------------------- packing
class Pack:
    """Priority-ordered sections under a token budget. Priority 0 is never dropped (but may be truncated)."""

    def __init__(self, title, budget):
        self.title, self.budget, self.items = title, budget, []

    def add(self, prio, head, body, src=None):
        if body and body.strip():
            self.items.append((prio, len(self.items), head, body.strip(), src))

    def render(self):
        out, used, dropped, forced = [f"# {self.title}"], tokens(self.title) + 2, [], False
        for prio, _, head, body, src in sorted(self.items):
            block = f"\n## {head}" + (f"  <{src}>" if src else "") + f"\n{body}"
            t = tokens(block)
            if used + t <= self.budget:
                out.append(block); used += t
            else:
                room = (self.budget - used - 15) * TOK
                if prio == 0 and not forced:          # must-have section: keep at least its start
                    room, forced = max(room, 300), True
                if room >= 200:
                    cut = block[:room].rsplit("\n", 1)[0]
                    out.append(cut + "\n… [truncated: --budget N or --full]"); used += tokens(cut) + 10
                else:
                    dropped.append(head)
        if dropped: out.append("\n## not included (budget)\n" + "; ".join(dropped))
        text = "\n".join(out)
        return text + f"\n\n(~{tokens(text)} tokens, budget {self.budget})"


# ----------------------------------------------------------------------------- engine
class Engine:
    def __init__(self, project):
        self.project = os.path.abspath(project)
        self.ix = Index(project)
        self.blocks = {b["id"]: b for b in S.load_blocks(project)}
        self.ledger = LG.read(project)
        self.lib = S.load_library()
        lay = os.path.join(self.project, "state", "layout.json")
        self.layout = _json(lay, {}).get("blocks", {})
        pj = os.path.join(self.project, "project.json")
        self.pj = _json(pj, {})

    # ---- derived facts
    def rules(self):
        c = self.ix.doc("AGENTS.md", "Never")
        return c["text"] if c else ""

    def net_map(self):
        m = collections.defaultdict(list)
        for bid, b in self.blocks.items():
            for p in b.get("parts", []):
                for num, net in p.get("pins", {}).items():
                    m[net].append((bid, f"{p['ref']}.{num}"))
        return m

    def state(self, bid):
        """Next gate derived from real state, not from the 'status' field."""
        b = self.blocks[bid]
        mpns = sorted({p.get("mpn") for p in b["parts"] if p.get("mpn")})
        unresolved = [m for m in mpns if m not in self.lib]
        nopins = [m for m in mpns if S.load_pins(m) is None]
        errs, warns = S.lint(self.project, bid)
        h = LG.block_hash(b, self.lib)
        built = bid in self.layout or any(e["type"] == "built" and e.get("block") == bid for e in self.ledger)
        ver = LG.verification_state(self.ledger, bid, h)
        if unresolved: gate, todo = "G2", f"python tools/resolve.py <P>  (unresolved: {', '.join(unresolved)})"
        elif nopins: gate, todo = "G3", f"python tools/pins.py --mpn {' '.join(nopins)}  then rewrite pin maps"
        elif any("QA" in e or "qa" in e for e in errs) or not b.get("qa"): gate, todo = "G4", "fill / fix qa[] from datasheets"
        elif errs: gate, todo = "G5", "fix lint errors below, then python tools/lint.py <P> " + bid
        elif not built: gate, todo = "G6", f"python tools/build.py <P> {bid}"
        elif ver != "fresh": gate, todo = "G7", f"python tools/verify.py <P> {bid}" + ("  (spec changed since last verify: STALE)" if ver == "stale" else "")
        elif b.get("status") != "accepted": gate, todo = "ACCEPT", "set status accepted, RESULT.md row, EasyEDA revision, git commit"
        else: gate, todo = "DONE", "-"
        return {"gate": gate, "todo": todo.replace("<P>", _rel(self.project)),
                "errors": errs, "warnings": warns, "hash": h, "built": built, "verified": ver}

    def gate_doc(self, gate):
        title = {"G2": "G2", "G3": "G3", "G4": "G4", "G5": "G5", "G6": "G6", "G7": "G7", "ACCEPT": "ACCEPT"}.get(gate)
        return self.ix.doc("docs/03_BLOCK_WORKFLOW.md", title) if title else None

    def ledger_for(self, bid=None, limit=None):
        sup = LG.superseded(self.ledger); out = []
        for e in self.ledger:
            if bid and e.get("block") != bid: continue
            st = "superseded" if e["id"] in sup else None
            if e["type"] in ("verified", "built") and e.get("block") in self.blocks:
                cur = LG.block_hash(self.blocks[e["block"]], self.lib)
                st = st or ("fresh" if e.get("spec_hash") == cur else "stale")
            out.append(fmt_ledger(e, st))
        return out[-limit:] if limit else out

    # ---- task packs
    def brief(self, budget=1500):
        P = Pack(f"BRIEF {self.pj.get('name', os.path.basename(self.project))}", budget)
        reqs = list(self.ix.chunks("req"))
        open_r = [c["title"] + ":" + c.get("status", "?") for c in reqs if c.get("status") != "CONFIRMED"]
        gateR = "no REQUIREMENTS.md rows" if not reqs else (f"{len(reqs)} reqs, open: {', '.join(open_r)}" if open_r else f"{len(reqs)} reqs all CONFIRMED")
        bom = os.path.join(self.project, "BOM_SELECTION.md")
        chosen = 0
        if os.path.exists(bom):
            with open(bom, encoding="utf-8") as f: chosen = f.read().count("✅")
        uu = "sheet_uuid " + ("set" if "REPLACE" not in self.pj.get("sheet_uuid", "REPLACE") and "PASTE" not in self.pj.get("sheet_uuid", "PASTE") else "NOT SET")
        P.add(0, "project", f"gate R: {gateR}\ngate B: {chosen} key parts chosen in BOM_SELECTION.md\n{uu}\n"
                            f"blocks: {len(self.blocks)}, ledger entries: {len(self.ledger)}")
        dp_path = os.path.join(self.project, "design_profile.json")
        dom = {}
        if os.path.exists(dp_path):
            try:
                with open(dp_path, encoding="utf-8") as f:
                    dom = (json.load(f).get("domain_profile") or {})
            except (OSError, ValueError):
                dom = {}
        if dom.get("primary_archetype"):
            P.add(0, "domain (DDIS)", f"archetype {dom['primary_archetype']} + {dom.get('secondary_archetypes', [])}; overlays {dom.get('overlays', [])}\n"
                                      f"rules: {len(dom.get('enforced_rule_ids', []))} enforced, {len(dom.get('advisory_rule_ids', []))} advisory, "
                                      f"{len(dom.get('unsupported_rule_ids', []))} unsupported; status {dom.get('status', '?')}\n"
                                      f"context: python tools/desk.py domains rules {dom['primary_archetype']}")
        else:
            P.add(1, "domain (DDIS)", "not classified yet -> python tools/desk.py domains validate " + _rel(self.project) + "/REQUIREMENTS.md --project " + _rel(self.project))
        order = self.pj.get("block_order") or sorted(self.blocks)
        rows, nxt = [], None
        for bid in [x for x in order if x in self.blocks] + sorted(set(self.blocks) - set(order)):
            st = self.state(bid); b = self.blocks[bid]
            rows.append(f"{bid:16s} {b.get('title', '')[:28]:28s} parts={len(b['parts']):<3d} next={st['gate']:6s} lint_err={len(st['errors'])} verify={st['verified']}")
            if nxt is None and st["gate"] != "DONE": nxt = (bid, st)
        P.add(0, "blocks (state derived from library/pins/lint/layout/ledger)", "\n".join(rows) or "none yet - see BLOCK_PLAN.md")
        if nxt:
            P.add(0, "next action", f"{nxt[0]}: gate {nxt[1]['gate']} -> {nxt[1]['todo']}\n"
                                    f"get its pack: python tools/ctx.py {_rel(self.project)} block {nxt[0]}")
        from desk import ops
        pend = ops.pending(self.project)
        if pend:
            P.add(0, "PENDING live operations (recover first)", "; ".join(f"{r['op']} {r['target']} op={r['id']}" + (" DIRTY" if r.get("dirty") else "") for r in pend)
                  + " -> python tools/desk.py recover " + _rel(self.project))
        P.add(1, "rules (AGENTS.md)", self.rules(), "AGENTS.md#never")
        led = [l for l in self.ledger_for() if "[built" not in l and "[verified" not in l]
        P.add(2, "recent decisions / facts (LEDGER)", "\n".join(led[-8:]))
        return P.render()

    def block(self, bid, budget=3000, full=False):
        if bid not in self.blocks:
            hit = [k for k in self.blocks if k.startswith(bid) or k.split("_", 1)[-1] == bid]
            if len(hit) != 1: raise SystemExit(f"block '{bid}' not found. Blocks: {', '.join(self.blocks)}")
            bid = hit[0]
        b, st = self.blocks[bid], self.state(bid)
        P = Pack(f"BLOCK {bid} — next gate {st['gate']}", 10 ** 9 if full else budget)
        P.add(0, "task", f"{st['todo']}\nspec file: {_rel(os.path.join(self.project, 'blocks', b['_file']))}"
                         f"  spec_hash={st['hash']}  built={st['built']}  verify={st['verified']}")
        if st["errors"] or st["warnings"]:
            P.add(0, "live lint", "\n".join([f"ERROR {e}" for e in st["errors"]] + [f"WARN  {w}" for w in st["warnings"]]))
        P.add(0, "spec (compact)", render_block(b), f"blocks/{b['_file']}")
        # neighbours through ports
        nm, lines = self.net_map(), []
        for port in b.get("ports", []):
            peers = [f"{ob}:{pin}" for ob, pin in nm.get(port, []) if ob != bid]
            lines.append(f"{port} -> " + (", ".join(peers[:8]) + (f" (+{len(peers) - 8})" if len(peers) > 8 else "") if peers else "(no other block yet)"))
        P.add(1, "ports -> other blocks", "\n".join(lines))
        # requirements + BOM study referencing this block's requirements
        reqs = [self.ix.get(f"req:{r}") for r in b.get("requirements", [])]
        P.add(1, "requirements served", "\n".join(c["text"] for c in reqs if c) or
              ("(block lists no 'requirements' IDs)" if not b.get("requirements") else "(IDs not found in REQUIREMENTS.md)"))
        bom = [c for c in self.ix.chunks("doc") if c["src"].startswith("project/BOM_SELECTION.md") and
               (set(c["refs"]) & set(b.get("requirements", [])) or any(p.get("mpn") and p["mpn"] in c["text"] for p in b["parts"]))]
        for c in bom[:2]: P.add(2, f"BOM selection: {c['title']}", c["text"], c["src"])
        led = self.ledger_for(bid)
        P.add(1, "ledger for this block", "\n".join(led[-10:]))
        if st["gate"] in ("G2", "G3", "G4", "G5"):
            pins = []
            for m in sorted({p["mpn"] for p in b["parts"] if p.get("mpn")}):
                pc = S.load_pins(m)
                if pc and len(pc) > 2: pins.append(f"{m}: " + " ".join(f"{q['num']}={q['name']}" for q in pc))
            P.add(1, "real symbol pins (library/pins)", "\n".join(pins))
        g = self.gate_doc(st["gate"])
        if g: P.add(2, f"how-to: {g['title']}", g["text"], g["src"])
        if st["gate"] == "G4":
            sel = self.ix.doc("docs/00b_COMPONENT_SELECTION.md", "Passive selection")
            if sel: P.add(3, "passive rules", sel["text"], sel["src"])
        P.add(4, "rules (AGENTS.md)", self.rules(), "AGENTS.md#never")
        return P.render()

    def net(self, name, budget=1200):
        nm = self.net_map()
        hits = nm.get(name) or []
        if not hits:
            near = [n for n in nm if name.upper() in n.upper()]
            return f"net {name}: not in any block." + (f" Similar: {', '.join(sorted(near)[:12])}" if near else "")
        by = collections.defaultdict(list)
        for bid, pin in hits: by[bid].append(pin)
        P = Pack(f"NET {name} — {len(hits)} pins in {len(by)} blocks", budget)
        P.add(0, "connections", "\n".join(f"{bid}: {' '.join(p)}" for bid, p in by.items()))
        port_of = [bid for bid, b in self.blocks.items() if name in b.get("ports", [])]
        P.add(0, "declared as port in", ", ".join(port_of) or "none (internal net)")
        if len(hits) == 1: P.add(0, "warning", "single-pin net: missing connection unless the other side is not specified yet")
        return P.render()

    def req(self, rid, budget=1500):
        c = self.ix.get(f"req:{rid}")
        P = Pack(f"REQUIREMENT {rid}", budget)
        P.add(0, "requirement", c["text"] if c else "not found in REQUIREMENTS.md", c and c["src"])
        users = [f"{bid} {b.get('title', '')}" for bid, b in self.blocks.items() if rid in b.get("requirements", [])]
        P.add(0, "served by blocks", "\n".join(users) or "none -> requirement not yet covered by any block")
        for d in [c for c in self.ix.chunks("doc") if rid in c["refs"] and c["src"].startswith("project/")][:3]:
            P.add(1, f"mentioned in {d['src']}", d["text"], d["src"])
        return P.render()

    def find(self, query, k=6, budget=1500):
        P = Pack(f"FIND \"{query}\"", budget)
        for rank, (s, c) in enumerate(self.ix.find(query, k)):
            body = c["text"] if c["kind"] in ("req", "ledger") else _snippet(c["text"], query)
            P.add(rank, f"{c['kind']}: {c['title']}  (score {s:.1f})", body, c["src"])
        if not P.items: P.add(0, "no match", "try other words, or `ctx.py <P> doc <heading>`")
        return P.render()

    def doc(self, query, budget=2500):
        q = query.lower()
        cands = [c for c in self.ix.chunks("doc") if q in c["title"].lower() or q in c["src"].lower()]
        if not cands: cands = [c for _, c in self.ix.find(query, 1, kinds=("doc",))]
        P = Pack(f"DOC {query}", budget)
        for i, c in enumerate(cands[:3]): P.add(i, c["title"], c["text"], c["src"])
        return P.render()

    def delta(self, budget=2000, mark=True):
        served_f = os.path.join(self.project, "state", "ctx_served.json")
        old = _json(served_f)
        now = {c["id"]: _sha(c["text"].encode()) for c in self.ix.chunks()}
        P = Pack("DELTA since last pack", budget)
        if old is None:
            P.add(0, "first run", "no previous pack recorded; start with `ctx.py <P> brief`. Baseline saved.")
        else:
            new = [i for i in now if i not in old]; chg = [i for i in now if i in old and old[i] != now[i]]
            gone = [i for i in old if i not in now]
            for i in new + chg:
                c = self.ix.get(i)
                tag = "NEW" if i in new else "CHANGED"
                body = render_block(self.blocks[c["refs"][0]]) if c["kind"] == "block" and c["refs"][0] in self.blocks else c["text"]
                P.add(0 if c["kind"] in ("block", "ledger", "req") else 2, f"{tag} {c['kind']}: {c['title']}", body, c["src"])
            if gone: P.add(1, "REMOVED", "\n".join(gone))
            if not (new or chg or gone): P.add(0, "no changes", "context you already have is current")
        if mark:
            _dump(now, served_f)
        return P.render()

    def policy(self, model_id, task_type="general", budget=1200):
        """Compile and serve compact mental-model policy (M1-M6) under budget."""
        from desk.mental.compiler import PolicyCompiler
        from desk.profile import DesignProfile

        prof_path = os.path.join(self.project, "design_profile.json")
        if os.path.exists(prof_path):
            profile = DesignProfile.load(prof_path)
        else:
            plan_path = os.path.join(self.project, "placement.json")
            plan = _json(plan_path, {})
            board_mm = tuple(plan.get("board_mm", [50.0, 50.0]))
            profile = DesignProfile(
                project_id=os.path.basename(os.path.abspath(self.project)),
                board_dimensions_mm=board_mm
            )

        compiled = PolicyCompiler.compile(model_id, task_type, profile)
        P = Pack(f"POLICY {model_id} ({task_type})", budget)
        P.add(0, f"Policy {compiled.policy_id}", compiled.to_compact_prompt())
        P.add(1, "Output Schema", json.dumps(compiled.output_schema, indent=1))
        return P.render()


def _snippet(text, query, width=700):
    words = [w for w in re.findall(r"[a-z0-9+_.\-]+", query.lower()) if len(w) > 1]
    low = text.lower(); pos = min([low.find(w) for w in words if low.find(w) >= 0] or [0])
    start = max(0, low.rfind("\n", 0, max(0, pos - 200)) + 1)
    s = text[start:start + width]
    return s + (" …" if start + width < len(text) else "")


# ----------------------------------------------------------------------------- EasyEDA API lookup (learned: agents
# read the 180k-token SKILL.md / class docs whole in 27 sessions; this answers the same question in ~100 tokens)
API_REF_DEFAULT = os.path.join(os.path.expanduser("~"), ".agents", "skills", "easyeda-api", "references", "_quick-reference.md")


def api_index():
    """{ 'sch_PrimitiveComponent.create': signature } built from the local EasyEDA API quick reference (cached)."""
    cache = os.path.join(ROOT, "library", "api_signatures.json")
    from desk import config as deskcfg
    ref = deskcfg.get("EASYEDA_API_REF") or API_REF_DEFAULT
    if os.path.exists(cache) and (not os.path.exists(ref) or os.path.getmtime(cache) >= os.path.getmtime(ref)):
        return _json(cache, {})
    idx, cls = {}, None
    if os.path.exists(ref):
        with open(ref, encoding="utf-8") as f:
            for ln in f:
                m = re.match(r"^## (\w+)", ln)
                if m:
                    c = m.group(1); cls = (c.split("_", 1)[0].lower() + "_" + c.split("_", 1)[1]) if "_" in c and not c.startswith("I") else c
                    continue
                m = re.match(r"^- \*\*(\w+)\*\*: `(.*)`", ln.strip())
                if cls and m:
                    sig = re.sub(r"\s+", " ", m.group(2)).replace("function ", "")
                    name = sig.split("(", 1)[0].strip()
                    idx[f"{cls}.{name}"] = sig[:300]
        _dump(idx, cache)
    return idx


def api_lookup(query, budget=600):
    """Method signatures + whether the method exists in the live client (api_map) + live-verified status."""
    idx = api_index()
    live = _json(os.path.join(ROOT, "library", "api_map.json"), {}).get("modules", {})
    ver = _json(os.path.join(ROOT, "library", "api_verified.json"), {}).get("calls", {})
    q = query.lower().replace("eda.", "")
    names = set(idx) | {f"{m}.{f}" for m, fs in live.items() for f in fs}
    hit = sorted(n for n in names if q in n.lower())
    if not hit:
        words = [w for w in re.split(r"[\s._]+", q) if w]
        hit = sorted(n for n in names if all(w in n.lower() for w in words))
    P = Pack(f"API {query} — {len(hit)} match(es)", budget)
    lines = []
    for n in hit[:40]:
        m, f = n.split(".", 1)
        exists = "live" if f in live.get(m, []) else ("NOT IN LIVE CLIENT" if live else "live map missing (tools/api_probe.py)")
        v = ver.get(n)
        vs = f" | verified {'OK' if v['ok'] else 'FAILED'}: {v['observed']}" if v else ""
        lines.append(f"eda.{n}  [{exists}{vs}]  {idx.get(n, '(no signature in reference)')}")
    P.add(0, "methods", "\n".join(lines) or "no match; try a module name (sch_Drc) or a verb (getGerber)")
    if len(hit) > 40: P.add(1, "more", f"{len(hit) - 40} more — narrow the query")
    return P.render()
