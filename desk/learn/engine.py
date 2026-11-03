"""DESK Learning Engine — learn from real agent sessions + DESK execution evidence, propose, human-gate, verify.

Inspired by Backpass (github.com/kunchenguid/backpass, MIT): evidence-only claims, >=2 distinct sessions before an
instruction changes, persistent corroboration ledger, remembered rejections, token budget, one writer module.
Different from Backpass by design:
  * Transcript parsing is NOT duplicated — Backpass's adapters are called through desk/learn/collect.mjs.
  * Detection is deterministic (no model calls): signals come from tool calls, results, errors, sizes and DESK's own
    logs (telemetry, ledger, op journal). Every finding carries verbatim, redacted quotes with session+event provenance.
  * Targets are DESK surfaces: agent instructions, context engine, tool interfaces, workflows, model routing.
  * Engineering rules (lint/ERC/calc/release gates/style) are PROTECTED: proposals against them become review tasks,
    never edits. Only two text surfaces can be edited on accept, both inside marked sections, and every accept runs
    the regression tests and reverts on failure.
State (local, git-ignored): .desk_learn/{corpus.jsonl,known.json,gaps.json,decisions.jsonl,report.md,tasks/}
"""
import collections, hashlib, json, os, re, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STATE = os.path.join(ROOT, ".desk_learn")
DEFAULTS = {
    "roots": [ROOT], "since_days": 365,
    "large_output_tokens": 4000,     # a single tool result above this is a waste candidate
    "retry_threshold": 3,            # same failing command head N times in one session
    "min_sessions": 2,               # corroboration floor (cannot be lowered below 2 for instruction edits)
    "instruction_budget_tokens": 2600,  # AGENTS.md always-loaded budget
    "backpass_dir": os.path.join(ROOT, "library", "tools", "backpass"),
}
PROTECTED = ("desk/spec.py", "desk/erc.py", "desk/calc.py", "desk/netcheck.py", "desk/release.py", "desk/draw.py",
             "docs/02_SCHEMATIC_STYLE.md", "tools/release.py", "tools/verify.py")
EDITABLE = {"AGENTS.md": "## Learned rules (human-approved)", "docs/06_EASYEDA_API.md": "## Learned gotchas (human-approved)"}
TOK = 4


def cfg():
    c = dict(DEFAULTS)
    f = os.path.join(STATE, "config.json")
    if os.path.exists(f):
        with open(f, encoding="utf-8") as h: c.update(json.load(h))
    c["min_sessions"] = max(2, int(c["min_sessions"]))
    return c


def _rj(path, default):
    if not os.path.exists(path): return default
    with open(path, encoding="utf-8") as f: return json.load(f)


def _wj(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(obj, f, indent=1)
    os.replace(tmp, path)


def _jsonl(path):
    if not os.path.exists(path): return []
    with open(path, encoding="utf-8") as f: return [json.loads(l) for l in f if l.strip()]


# ----------------------------------------------------------------------------- 1. collect (via Backpass adapters)
def collect(c=None):
    c = c or cfg()
    bp = c["backpass_dir"]
    if not os.path.exists(os.path.join(bp, "src", "discovery", "index.js")):
        raise SystemExit(f"Backpass not found at {bp}. Run: python tools/learn.py setup")
    os.makedirs(STATE, exist_ok=True)
    known_f, corpus_f, raw = os.path.join(STATE, "known.json"), os.path.join(STATE, "corpus.jsonl"), os.path.join(STATE, "raw.jsonl")
    if not os.path.exists(known_f): _wj(known_f, {})
    t0 = time.time()
    p = subprocess.run(["node", os.path.join(ROOT, "desk", "learn", "collect.mjs"), bp, raw, json.dumps(c["roots"]),
                        str(c["since_days"]), known_f], capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0: raise SystemExit("collector failed: " + p.stderr[-800:])
    stats = json.loads(p.stdout.strip().splitlines()[-1])
    corpus = {s["key"]: s for s in _jsonl(corpus_f)}
    new = _jsonl(raw)
    for s in new: corpus[s["key"]] = s
    with open(corpus_f + ".tmp", "w", encoding="utf-8") as f:
        for s in corpus.values(): f.write(json.dumps(s) + "\n")
    os.replace(corpus_f + ".tmp", corpus_f)
    known = _rj(known_f, {}); known.update({s["key"]: s["sig"] for s in new}); _wj(known_f, known)
    os.remove(raw)
    stats.update(new_or_changed=len(new), corpus=len(corpus), seconds=round(time.time() - t0, 2))
    return stats


# ----------------------------------------------------------------------------- 2. detect (deterministic signals)
ERR_RX = re.compile(r"(Traceback \(most recent|SyntaxError|NameError|TypeError|KeyError|EDA error|STOP:|is not a function|"
                    r"ECONNREFUSED|timed out|Timeout|command not found|No such file|Permission denied|FAIL\b|ERROR\b|"
                    r"exited with code [1-9])")
CMD_TOOLS = ("bash", "shell", "exec", "execute", "run_terminal_cmd", "powershell", "terminal")
DOCS_READ_RX = re.compile(r"(SKILL\.md|_quick-reference\.md|references[\/].*\.md)$", re.I)
DRAW_RX = re.compile(r"eda\.sch_Primitive(Component\.create|Wire\.create|Attribute\.createNetLabel)")
DOC_RX = re.compile(r"(AGENTS\.md|CLAUDE\.md|README\.md|docs[\\/][0-9]\w+\.md|blocks[\\/]\w+\.json)$")
API_RX = re.compile(r"eda\.(\w+)\.(\w+)")


def _head(e):
    """Stable short signature of a tool call: tool + command head / file name."""
    name = (e.get("name") or "?").lower()
    inp = e.get("input") or ""
    try: d = json.loads(inp)
    except (ValueError, TypeError): d = {}
    if isinstance(d, dict):
        if d.get("command"):
            cmd = re.sub(r"^(cd [^;&]+[;&]+\s*)+", "", d["command"].strip())
            cmd = re.sub(r"^timeout \d+ ", "", cmd)
            toks = re.findall(r"[\w./\\-]+", cmd)[:3]
            toks = [os.path.basename(t) if ("/" in t or "\\" in t) else t for t in toks]
            return f"{name}:{' '.join(toks)}"
        for k in ("path", "file_path", "filePath"):
            if d.get(k): return f"{name}:{os.path.basename(str(d[k]))}"
    return name


def _quote(text, rx=None, n=240):
    if not text: return ""
    if rx:
        m = rx.search(text)
        if m:
            s = max(0, text.rfind("\n", 0, m.start()) + 1)
            return text[s:s + n].strip()
    return text[:n].strip()


def _norm_err(q):
    q = re.sub(r"[A-Za-z]:[\\/][^\s'\"]+|/[\w./-]{6,}", "<path>", q)
    q = re.sub(r"\b[0-9a-f]{8,}\b|\d+", "#", q)
    return q[:90]


def detect(session, c):
    """Return list of findings: {sig, kind, target, quote, event, measured_tokens}."""
    F = []
    ev = session["events"]
    tools = [e for e in ev if e["kind"] == "tool"]
    seen_inputs = {}
    fails = collections.Counter()
    for e in tools:
        head = _head(e)
        rtok = (e.get("resultChars") or 0) // TOK
        # token waste: oversized tool output
        pth0 = ""
        try:
            d0 = json.loads(e.get("input") or "")
            pth0 = str(d0.get("path") or d0.get("file_path") or "") if isinstance(d0, dict) else ""
        except (ValueError, TypeError): pass
        if DOCS_READ_RX.search(pth0.replace("\\", "/")) and rtok >= 1000:
            F.append(dict(sig=f"reference_read|{os.path.basename(pth0)}", kind="reference_read", target="context", event=e["i"],
                          quote=f"read {pth0} ({rtok} tokens)", measured_tokens=rtok))
        elif rtok >= c["large_output_tokens"]:
            F.append(dict(sig=f"large_output|{head}", kind="large_output", target="tool-interface", event=e["i"],
                          quote=_quote(e.get("input"), n=200), measured_tokens=rtok))
        # unnecessary calls: identical call repeated with nothing changed in between (same input, same result size)
        k = (e.get("name"), e.get("input"))
        if k in seen_inputs and seen_inputs[k] == e.get("resultChars"):
            F.append(dict(sig=f"repeated_call|{head}", kind="repeated_call", target="workflow", event=e["i"],
                          quote=_quote(e.get("input"), n=200), measured_tokens=rtok + (e.get("inputChars") or 0) // TOK))
        seen_inputs[k] = e.get("resultChars")
        # failures
        res = e.get("result") or ""
        is_cmd = '"command"' in (e.get("input") or "") or (e.get("name") or "").lower() in CMD_TOOLS
        if e.get("status") == "error" or (is_cmd and ERR_RX.search(res[-1500:])):
            q = _quote(res, ERR_RX)
            fails[head] += 1
            F.append(dict(sig=f"failure|{head}|{_norm_err(q)}", kind="failure", target="workflow", event=e["i"], quote=q,
                          measured_tokens=rtok))
            for m in API_RX.finditer((e.get("input") or "")[:4000]):
                if "is not a function" in res or "EDA error" in res:
                    F.append(dict(sig=f"eda_api_failure|{m.group(1)}.{m.group(2)}", kind="eda_api_failure", target="api-map",
                                  event=e["i"], quote=q, measured_tokens=0)); break
        # rule violations against AGENTS.md (model writes its own drawing JS outside tools/)
        inp = e.get("input") or ""
        if DRAW_RX.search(inp) and "tools/build.py" not in inp and "desk/draw.py" not in inp and session.get("era") == "desk":
            F.append(dict(sig="rule_violation|own_drawing_js", kind="rule_violation", target="instruction", event=e["i"],
                          quote=_quote(inp, DRAW_RX), measured_tokens=(e.get("inputChars") or 0) // TOK))
        # context bypass: reading whole DESK docs/specs instead of tools/ctx.py
        try: d = json.loads(inp)
        except (ValueError, TypeError): d = {}
        pth = str(d.get("path") or d.get("file_path") or "") if isinstance(d, dict) else ""
        if (e.get("name") or "").lower() in ("read", "read_file", "view") and DOC_RX.search(pth.replace("\\", "/")) and session.get("underRoot"):
            F.append(dict(sig=f"context_bypass|{os.path.basename(pth)}", kind="context_bypass", target="context", event=e["i"],
                          quote=f"read {pth}", measured_tokens=rtok))
    for head, n in fails.items():
        if n >= c["retry_threshold"]:
            F.append(dict(sig=f"retry_loop|{head}", kind="retry_loop", target="workflow", event=None,
                          quote=f"{n} failing calls of `{head}` in one session", measured_tokens=0))
    return F


def session_metrics(s):
    tools = [e for e in s["events"] if e["kind"] == "tool"]
    return {"tools": len(tools), "result_tokens": sum((e.get("resultChars") or 0) for e in tools) // TOK,
            "input_tokens": sum((e.get("inputChars") or 0) for e in tools) // TOK,
            "assistant_tokens": sum(e.get("textChars") or 0 for e in s["events"] if e["kind"] == "message" and e.get("role") == "assistant") // TOK,
            "errors": sum(1 for e in tools if e.get("status") == "error" or ERR_RX.search((e.get("result") or "")[:4000]))}


def desk_execution_evidence():
    """DESK's own logs: tool telemetry, op journals, ledgers. Returns findings with file provenance."""
    F = []
    runs = _jsonl(os.path.join(STATE, "runs.jsonl"))
    by = collections.defaultdict(list)
    for r in runs: by[r["tool"]].append(r)
    for tool, rs in by.items():
        bad = [r for r in rs if r.get("rc") not in (0, None)]
        if len(rs) >= 3 and len(bad) / len(rs) >= 0.5:
            F.append(dict(sig=f"tool_failure_rate|{tool}", kind="tool_failure_rate", target="tool-interface", event=None,
                          quote=f"{len(bad)}/{len(rs)} runs of {tool} exited non-zero", measured_tokens=0, source="runs.jsonl"))
        big = [r for r in rs if (r.get("out_chars") or 0) // TOK >= 2000]
        if big:
            F.append(dict(sig=f"large_output|tool:{tool}", kind="large_output", target="tool-interface", event=None,
                          quote=f"{tool} printed {max(r['out_chars'] for r in big) // TOK} tokens", measured_tokens=sum(r["out_chars"] for r in big) // TOK,
                          source="runs.jsonl"))
    for jf in _glob(os.path.join(ROOT, "projects", "*", "state", "ops.jsonl")) + _glob(os.path.join(ROOT, "examples", "*", "state", "ops.jsonl")):
        for r in _jsonl(jf):
            if r.get("phase") == "fail" and r.get("dirty"):
                F.append(dict(sig=f"dirty_write_failure|{r.get('op')}", kind="engineering_failure", target="workflow", event=None,
                              quote=f"{r.get('op')} {r.get('target')}: {str(r.get('error'))[:160]}", measured_tokens=0, source=os.path.relpath(jf, ROOT)))
    return F, runs


def desk_epoch_ms():
    """First DESK commit time: sessions before it could not have followed DESK rules (era = pre-desk)."""
    try:
        out = subprocess.run(["git", "-C", ROOT, "log", "--reverse", "--format=%ct"], capture_output=True, text=True).stdout.split()
        return int(out[0]) * 1000 if out else 0
    except (OSError, ValueError):
        return 0


def _glob(p):
    import glob
    return glob.glob(p)


# ----------------------------------------------------------------------------- 3. corroborate (gap ledger)
def analyze(c=None):
    c = c or cfg()
    corpus = _jsonl(os.path.join(STATE, "corpus.jsonl"))
    gaps_f = os.path.join(STATE, "gaps.json")
    gaps = _rj(gaps_f, {})
    per_model = collections.defaultdict(lambda: collections.Counter())
    totals = collections.Counter()
    epoch = desk_epoch_ms()
    for s in corpus:
        s["era"] = "desk" if (s.get("startedAt") or 0) >= epoch else "pre-desk"
        m = session_metrics(s)
        mk = s.get("model") or "unknown"
        per_model[mk].update(sessions=1, **m)
        totals.update(sessions=1, **m, **{f"sessions_{s['era']}": 1})
        for f in detect(s, c):
            g = gaps.setdefault(f["sig"], {"kind": f["kind"], "target": f["target"], "sessions": {}, "measured_tokens": 0,
                                            "first_seen": time.strftime("%Y-%m-%d")})
            sid = s["key"]
            ent = g["sessions"].setdefault(sid, {"model": mk, "quotes": [], "count": 0, "tokens": 0})
            # idempotent per (session, event): re-analysis never double counts
            evk = f"{f['event']}"
            if evk not in {q["event"] for q in ent["quotes"]}:
                ent["count"] += 1; ent["tokens"] += f["measured_tokens"]
                if len(ent["quotes"]) < 3: ent["quotes"].append({"event": evk, "quote": f["quote"]})
            g["last_seen"] = time.strftime("%Y-%m-%d")
    ex_f, runs = desk_execution_evidence()
    for f in ex_f:
        g = gaps.setdefault(f["sig"], {"kind": f["kind"], "target": f["target"], "sessions": {}, "measured_tokens": 0,
                                        "first_seen": time.strftime("%Y-%m-%d")})
        g["sessions"][f"desk-log:{f['source']}"] = {"model": "desk", "quotes": [{"event": f["source"], "quote": f["quote"]}],
                                                   "count": 1, "tokens": f["measured_tokens"]}
    for g in gaps.values():
        g["measured_tokens"] = sum(v["tokens"] for v in g["sessions"].values())
        g["n_sessions"] = len(g["sessions"])
        g["occurrences"] = sum(v["count"] for v in g["sessions"].values())
    _wj(gaps_f, gaps)
    summary = {"totals": dict(totals), "per_model": {k: dict(v) for k, v in per_model.items()}, "runs": len(runs)}
    _wj(os.path.join(STATE, "metrics.json"), summary)
    return gaps, summary


# ----------------------------------------------------------------------------- 4. propose
def _pid(sig): return "P" + hashlib.sha1(sig.encode()).hexdigest()[:6]


def _template(sig, g):
    kind, rest = g["kind"], sig.split("|", 1)[1] if "|" in sig else sig
    tok = g["measured_tokens"]
    T = {
        "large_output": ("tool-interface", f"`{rest}` returned oversized output ({tok} tokens measured across {g['n_sessions']} sessions).",
                         f"Give `{rest}` a compact default (summary + --json/--full), or route this lookup through tools/ctx.py."),
        "repeated_call": ("workflow", f"Identical `{rest}` call repeated with an identical result ({g['occurrences']}x).",
                          f"Agent rule: do not re-run `{rest}` unless an input changed; reuse the previous result / ctx.py delta."),
        "failure": ("workflow", f"Recurring failure of `{rest.split('|')[0]}`: {rest.split('|')[1] if '|' in rest else ''}",
                    "Add a precondition check / clearer error with the fix to the tool, or a gotcha line for agents."),
        "retry_loop": ("workflow", f"Retry loop on `{rest}` (>= {cfg()['retry_threshold']} failures in one session).",
                       "Agent rule: after 2 identical failures stop and run the diagnostic (ctx.py block / tool --help) instead of retrying."),
        "eda_api_failure": ("api-map", f"EasyEDA call `{rest}` failed in real sessions.",
                            f"Gotcha: `{rest}` failed live; check library/api_map.json + api_verified.json before use."),
        "rule_violation": ("instruction", "Models wrote their own EasyEDA drawing JavaScript (AGENTS.md 'Never' rule 1).",
                           "Reinforce: 'All schematic drawing goes through `python tools/build.py`; never call eda.sch_Primitive*.create yourself.'"),
        "reference_read": ("context", f"Agents read the reference file `{rest}` whole ({tok} tokens across {g['n_sessions']} sessions).",
                           f"For EasyEDA API questions run `python tools/ctx.py api <method|module>`; never read `{rest}` whole."),
        "context_bypass": ("context", f"Whole-file reads of `{rest}` in DESK sessions ({tok} tokens).",
                           f"Serve `{rest}` content through a ctx.py pack (doc/find) and point agents to it."),
        "tool_failure_rate": ("tool-interface", f"DESK tool `{rest}` fails in >= 50% of runs.", "Investigate preconditions / error messages of the tool."),
        "engineering_failure": ("workflow", f"Live write `{rest}` failed after touching the design.", "Review recovery path (tools/desk.py recover) and preconditions."),
    }
    target, why, change = T.get(kind, ("workflow", sig, "Review."))
    files = {"tool-interface": ["tools/" + rest.split(":")[-1].split()[0]] if rest.startswith("bash:python") else [],
             "api-map": ["docs/06_EASYEDA_API.md"], "instruction": ["AGENTS.md"], "context": ["desk/context.py"]}.get(target, [])
    rule = None
    if target == "instruction" or kind in ("repeated_call", "retry_loop", "reference_read"):
        rule, edit_file = change.split(": ", 1)[-1].strip("'"), "AGENTS.md"
    elif target == "api-map":
        rule, edit_file = change.split(": ", 1)[-1], "docs/06_EASYEDA_API.md"
    else:
        edit_file = None
    protected = [f for f in files if any(f.startswith(p) or p.startswith(f) for p in PROTECTED if f)]
    return {"target": target, "why": why, "change": change, "files": files, "edit_file": edit_file, "rule": rule,
            "protected": bool(protected)}


def propose(gaps, c=None):
    c = c or cfg()
    dec = {}
    for d in _jsonl(os.path.join(STATE, "decisions.jsonl")): dec[d["id"]] = d
    props = []
    for sig, g in gaps.items():
        real = [k for k in g["sessions"] if not k.startswith("desk-log:")]
        enough = len(real) >= c["min_sessions"] or (any(k.startswith("desk-log:") for k in g["sessions"]) and g["kind"] in
                                                     ("tool_failure_rate", "engineering_failure", "large_output"))
        if not enough: continue
        pid = _pid(sig); d = dec.get(pid)
        if d and d["decision"] == "reject" and g["n_sessions"] <= d.get("n_sessions_at_decision", 0): continue
        if d and d["decision"] == "accept": continue
        t = _template(sig, g)
        ev = [{"session": k, "model": v["model"], **q} for k, v in list(g["sessions"].items())[:4] for q in v["quotes"][:1]]
        score = g["measured_tokens"] + 500 * g["n_sessions"] + (3000 if g["kind"] in ("rule_violation", "eda_api_failure") else 0)
        props.append({"id": pid, "sig": sig, "kind": g["kind"], "n_sessions": g["n_sessions"], "occurrences": g["occurrences"],
                      "measured_tokens": g["measured_tokens"], "score": score, "evidence": ev, **t,
                      "reproposed_after_reject": bool(d and d["decision"] == "reject")})
    props.sort(key=lambda p: -p["score"])
    _wj(os.path.join(STATE, "proposals.json"), props)
    return props


def routing(summary):
    """Model routing evidence (report only): per-model error rate, tools/session, output tokens/session."""
    rows = []
    for m, v in summary["per_model"].items():
        if v.get("sessions", 0) < 1 or v.get("tools", 0) < 10: continue
        rows.append({"model": m, "sessions": v["sessions"], "tools_per_session": round(v["tools"] / v["sessions"], 1),
                     "error_rate": round(v["errors"] / max(1, v["tools"]), 3),
                     "result_tokens_per_tool": round(v["result_tokens"] / max(1, v["tools"]))})
    rows.sort(key=lambda r: r["error_rate"])
    return rows


# ----------------------------------------------------------------------------- 5. human gate + verified apply
def decide(pid, decision, reason="", reviewer="", engineering_review=None):
    props = {p["id"]: p for p in _rj(os.path.join(STATE, "proposals.json"), [])}
    if pid not in props: raise SystemExit(f"unknown proposal {pid} (run: python tools/learn.py run)")
    p = props[pid]
    result = {"applied": False}
    if decision == "accept":
        if p["protected"] and not engineering_review:
            raise SystemExit("STOP: proposal touches a PROTECTED engineering surface; requires --engineering-review \"<name>\" "
                             "and is only ever turned into a task, never an automatic edit.")
        if p.get("edit_file") and p.get("rule") and not p["protected"]:
            result = apply_rule(p)
        else:
            result = write_task(p)
    rec = {"id": pid, "sig": p["sig"], "decision": decision, "reason": reason, "reviewer": reviewer,
           "engineering_review": engineering_review, "n_sessions_at_decision": p["n_sessions"], "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
           **{k: v for k, v in result.items() if k != "diff"}}
    os.makedirs(STATE, exist_ok=True)
    with open(os.path.join(STATE, "decisions.jsonl"), "a", encoding="utf-8") as f: f.write(json.dumps(rec) + "\n")
    return {**rec, "diff": result.get("diff")}


def write_task(p):
    d = os.path.join(STATE, "tasks"); os.makedirs(d, exist_ok=True)
    f = os.path.join(d, f"{p['id']}.md")
    with open(f, "w", encoding="utf-8") as h:
        h.write(f"# Learning task {p['id']} — {p['kind']} ({p['target']})\n\n{p['why']}\n\n**Proposed change:** {p['change']}\n\n"
                f"Files: {', '.join(p['files']) or '-'}{'  **PROTECTED: engineering review + regression tests required**' if p['protected'] else ''}\n\n"
                f"Measured: {p['measured_tokens']} tokens, {p['occurrences']} occurrences, {p['n_sessions']} sessions\n\n## Evidence\n")
        for e in p["evidence"]: h.write(f"- `{e['session']}` ({e['model']}) event {e['event']}: \"{e['quote']}\"\n")
        h.write("\nAcceptance: implement, add/adjust a test, `python -m unittest discover -s tests` green, then re-run `python tools/learn.py run` "
                "and confirm the signal drops.\n")
    return {"applied": False, "task": os.path.relpath(f, ROOT)}


def _tokens(path):
    with open(path, encoding="utf-8") as f: return len(f.read()) // TOK


def apply_rule(p, run_tests=True):
    """Append one rule line inside the editable section, with provenance; budget-checked; tests or revert."""
    rel = p["edit_file"]; path = os.path.join(ROOT, rel); header = EDITABLE[rel]
    with open(path, encoding="utf-8") as f: orig = f.read()
    line = f"- {p['rule']} <!-- learn:{p['id']} sessions={p['n_sessions']} -->"
    if f"learn:{p['id']}" in orig: return {"applied": False, "note": "already present"}
    text = orig if header in orig else orig.rstrip() + f"\n\n{header}\nEach line was accepted by a human from >= 2 sessions of evidence (tools/learn.py).\n"
    i = text.index(header) + len(header)
    j = text.find("\n## ", i); j = len(text) if j < 0 else j
    new = text[:j].rstrip() + "\n" + line + "\n" + text[j:]
    if rel == "AGENTS.md" and len(new) // TOK > cfg()["instruction_budget_tokens"]:
        raise SystemExit(f"STOP: AGENTS.md would be {len(new) // TOK} tokens > budget {cfg()['instruction_budget_tokens']}. "
                         "Remove or extract a rule first (zero-sum at budget).")
    with open(path, "w", encoding="utf-8") as f: f.write(new)
    mirror = os.path.join(ROOT, "CLAUDE.md") if rel == "AGENTS.md" else None
    if mirror: 
        with open(mirror, "w", encoding="utf-8") as f: f.write(new)
    if run_tests:
        t = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", os.path.join(ROOT, "tests")], cwd=ROOT,
                           capture_output=True, text=True, env={**os.environ, "DESK_TELEMETRY": "0"})
        if t.returncode != 0:
            with open(path, "w", encoding="utf-8") as f: f.write(orig)
            if mirror:
                with open(mirror, "w", encoding="utf-8") as f: f.write(orig)
            raise SystemExit("REVERTED: regression tests failed after applying the rule:\n" + t.stderr[-1500:])
    return {"applied": True, "file": rel, "diff": "+ " + line}


# ----------------------------------------------------------------------------- 6. report / benchmark
def report(props, summary, stats=None):
    t = summary["totals"]
    by_kind = collections.Counter(); tok_kind = collections.Counter()
    for p in props: by_kind[p["kind"]] += 1; tok_kind[p["kind"]] += p["measured_tokens"]
    L = [f"# DESK learning report ({time.strftime('%Y-%m-%d %H:%M')})", "",
         f"Corpus: {t.get('sessions', 0)} sessions, {t.get('tools', 0)} tool calls, "
         f"{t.get('result_tokens', 0)} tool-output tokens, {t.get('errors', 0)} failing calls; DESK tool runs logged: {summary['runs']}",
         (f"Collection: {stats}" if stats else ""), "",
         "## Proposals (corroborated by >= 2 sessions or DESK logs)",
         "| id | kind | target | sessions | occurrences | measured tokens | protected |", "|---|---|---|---|---|---|---|"]
    for p in props[:25]:
        L.append(f"| {p['id']} | {p['kind']} | {p['target']} | {p['n_sessions']} | {p['occurrences']} | {p['measured_tokens']} | {'yes' if p['protected'] else ''} |")
    L += ["", "## Measured waste addressed by proposals", *[f"- {k}: {by_kind[k]} proposals, {tok_kind[k]} tokens" for k in by_kind],
          f"- share of all tool-output tokens: {round(100 * sum(tok_kind.values()) / max(1, t.get('result_tokens', 1)), 1)}%", "",
          "## Model routing evidence (report only; no automatic routing change)",
          "| model | sessions | tools/session | error rate | result tokens/tool |", "|---|---|---|---|---|"]
    for r in routing(summary):
        L.append(f"| {r['model']} | {r['sessions']} | {r['tools_per_session']} | {r['error_rate']} | {r['result_tokens_per_tool']} |")
    text = "\n".join(l for l in L if l is not None)
    with open(os.path.join(STATE, "report.md"), "w", encoding="utf-8") as f: f.write(text + "\n")
    return text


def bench():
    """Replay measured reference reads against the ctx api pack that answers the same lookup (measured both sides).
    Only class-specific references (e.g. SCH_Document.md) are replayable; generic files (SKILL.md) are reported, not credited."""
    from desk.context import api_lookup, tokens
    gaps = _rj(os.path.join(STATE, "gaps.json"), {})
    rows, before, after, unrepl = [], 0, 0, 0
    for sig, g in gaps.items():
        if g["kind"] != "reference_read": continue
        fname = sig.split("|", 1)[1]
        m = re.match(r"^([A-Z]+)_(\w+)\.md$", fname)
        if not m:
            unrepl += g["measured_tokens"]; continue
        q = m.group(1).lower() + "_" + m.group(2)
        pack = tokens(api_lookup(q, budget=1200))
        n = g["occurrences"]
        rows.append((fname, n, g["measured_tokens"], pack * n)); before += g["measured_tokens"]; after += pack * n
    return {"rows": sorted(rows, key=lambda r: -r[2]), "before": before, "after": after, "not_replayable_tokens": unrepl}
