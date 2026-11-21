"""Learning Engine tests: detectors, corroboration, idempotence, era provenance, rejection memory, human gate,
protected surfaces, the single agent-memory writer (backpass apply), budget source, regression revert, and a real Backpass-adapter integration test (skipped if node/backpass
are missing). Offline. Run: python -m unittest discover -s tests -v"""
import json, os, re, shutil, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from desk.learn import engine as L  # noqa: E402
from desk.errors import ApprovalRequired, ConfigError, DeskError, UsageError  # noqa: E402

BIG = "x" * 20000


def _r(p):
    with open(p, encoding="utf-8") as f: return f.read()


def _rb(p):
    with open(p, "rb") as f: return f.read()


def tool(i, name, inp, res="", status="completed"):
    ij = json.dumps(inp)
    return {"i": i, "kind": "tool", "name": name, "input": ij, "inputChars": len(ij), "result": res[:4000],
            "resultChars": len(res), "status": status}


def session(key, events, model="m1", started=10 ** 13, under=True):
    return {"harness": "pi", "id": key, "key": f"pi:{key}", "sig": "1:1", "cwd": ROOT, "model": model,
            "startedAt": started, "underRoot": under, "usesDesk": True, "events": events}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._state, self._root = L.STATE, L.ROOT
        L.STATE = os.path.join(self.tmp, ".desk_learn"); os.makedirs(L.STATE)
        L.ROOT = self.tmp
        self.c = dict(L.DEFAULTS)

    def tearDown(self):
        L.STATE, L.ROOT = self._state, self._root
        shutil.rmtree(self.tmp, ignore_errors=True)

    def corpus(self, sessions):
        with open(os.path.join(L.STATE, "corpus.jsonl"), "w") as f:
            for s in sessions: f.write(json.dumps(s) + "\n")


class TestDetect(Base):
    def kinds(self, s):
        s.setdefault("era", "desk")
        return {f["kind"] for f in L.detect(s, self.c)}

    def test_large_output_and_repeat(self):
        s = session("a", [tool(0, "bash", {"command": "python tools/x.py"}, BIG), tool(1, "bash", {"command": "python tools/x.py"}, BIG)])
        self.assertEqual(self.kinds(s), {"large_output", "repeated_call"})

    def test_command_failure_detected_from_output_tail(self):
        s = session("a", [tool(0, "bash", {"command": "python tools/build.py P B"}, "ok\n" * 10 + "STOP: lint failed")])
        self.assertIn("failure", self.kinds(s))

    def test_reading_file_with_error_words_is_not_a_failure(self):
        s = session("a", [tool(0, "read", {"path": "src/a.js"}, "await Timeout(); throw new TypeError('x')")])
        self.assertNotIn("failure", self.kinds(s))

    def test_reference_read(self):
        s = session("a", [tool(0, "read", {"path": "refs/references/SCH_Document.md"}, "y" * 8000)])
        self.assertIn("reference_read", self.kinds(s))

    def test_rule_violation_only_in_desk_era(self):
        ev = [tool(0, "bash", {"command": "curl /execute -d 'await eda.sch_PrimitiveWire.create([0,0,1,1])'"}, "ok")]
        self.assertIn("rule_violation", self.kinds(session("a", ev)))
        pre = session("b", ev); pre["era"] = "pre-desk"
        self.assertNotIn("rule_violation", self.kinds(pre))

    def test_retry_loop(self):
        ev = [tool(i, "bash", {"command": f"python tools/verify.py P {i}"}, "Traceback (most recent call last):\nKeyError") for i in range(3)]
        self.assertIn("retry_loop", self.kinds(session("a", ev)))


class TestCorroboration(Base):
    def test_single_session_never_proposes_and_reanalysis_is_idempotent(self):
        ev = [tool(i, "read", {"path": "r/references/LIB_Device.md"}, "z" * 9000) for i in range(3)]
        self.corpus([session("a", ev)])
        g, _ = L.analyze(self.c); self.assertEqual(L.propose(g, self.c), [])
        sig = "reference_read|LIB_Device.md"
        occ = g[sig]["occurrences"]
        g2, _ = L.analyze(self.c)
        self.assertEqual(g2[sig]["occurrences"], occ)
        self.assertEqual(g2[sig]["n_sessions"], 1)

    def test_two_sessions_propose_with_provenance(self):
        ev = lambda: [tool(0, "read", {"path": "r/references/LIB_Device.md"}, "z" * 9000)]
        self.corpus([session("a", ev()), session("b", ev(), model="m2")])
        props = L.propose(L.analyze(self.c)[0], self.c)
        p = next(p for p in props if p["kind"] == "reference_read")
        self.assertEqual(p["n_sessions"], 2)
        self.assertEqual({e["session"] for e in p["evidence"]}, {"pi:a", "pi:b"})
        self.assertTrue(all(e["quote"] for e in p["evidence"]))

    def test_min_sessions_cannot_go_below_two(self):
        with open(os.path.join(L.STATE, "config.json"), "w") as f: json.dump({"min_sessions": 1}, f)
        self.assertEqual(L.cfg()["min_sessions"], 2)

    def test_rejection_remembered_until_new_evidence(self):
        ev = lambda: [tool(0, "read", {"path": "r/references/LIB_Device.md"}, "z" * 9000)]
        self.corpus([session("a", ev()), session("b", ev())])
        p = next(p for p in L.propose(L.analyze(self.c)[0], self.c) if p["kind"] == "reference_read")
        L.decide(p["id"], "reject", "not now", "tester")
        self.assertNotIn(p["id"], [x["id"] for x in L.propose(L.analyze(self.c)[0], self.c)])
        self.corpus([session("a", ev()), session("b", ev()), session("c", ev())])
        again = [x for x in L.propose(L.analyze(self.c)[0], self.c) if x["id"] == p["id"]]
        self.assertTrue(again and again[0]["reproposed_after_reject"])


POINTER = "# DESK Instructions for Claude Code\n\n<!-- Canonical instructions maintained in AGENTS.md and optimized via Backpass -->\n@AGENTS.md\n"
GOTCHAS = "docs/06_EASYEDA_API.md"


class TestHumanGate(Base):
    def make_root(self, failing_test=False, claude=POINTER, budget=None):
        r = os.path.join(self.tmp, "repo"); os.makedirs(os.path.join(r, "tests")); os.makedirs(os.path.join(r, "docs"))
        with open(os.path.join(r, "AGENTS.md"), "w", newline="") as f: f.write("# AGENTS\n\n## Never\n1. x\n")
        with open(os.path.join(r, "CLAUDE.md"), "w", newline="") as f: f.write(claude)
        with open(os.path.join(r, GOTCHAS), "w", newline="") as f: f.write("# API\n\n## Calls\nx\n")
        if budget is not None:
            with open(os.path.join(r, ".backpassrc.json"), "w") as f: json.dump({"budgetTokens": budget}, f)
        with open(os.path.join(r, "tests", "test_ok.py"), "w") as f:
            f.write("import unittest\nclass T(unittest.TestCase):\n    def test(self): self.assertTrue(" + ("False" if failing_test else "True") + ")\n")
        L.ROOT = r
        return r

    def snapshot(self, r):
        return {n: _rb(os.path.join(r, n)) for n in ("AGENTS.md", "CLAUDE.md", GOTCHAS)}

    def prop(self, **kw):
        p = {"id": "Ptest01", "sig": "s", "kind": "reference_read", "n_sessions": 2, "occurrences": 2, "measured_tokens": 10,
             "edit_file": "AGENTS.md", "rule": "Use tools/ctx.py api.", "protected": False, "target": "context", "why": "w",
             "change": "c", "files": [], "evidence": [{"session": "pi:a", "model": "m", "event": "0", "quote": "q"}]}
        p.update(kw)
        with open(os.path.join(L.STATE, "proposals.json"), "w") as f: json.dump([p], f)
        return p

    def test_agents_target_accept_writes_task_and_leaves_memory_byte_identical(self):
        r = self.make_root(budget=4321); self.prop(); before = self.snapshot(r)
        res = L.decide("Ptest01", "accept", reviewer="tester")
        self.assertFalse(res["applied"])
        self.assertTrue(res["task"].replace(os.sep, "/").endswith(".desk_learn/tasks/Ptest01.md"))
        self.assertEqual(self.snapshot(r), before)
        task = _r(os.path.join(L.STATE, "tasks", "Ptest01.md"))
        self.assertIn("backpass apply", task)
        self.assertIn("Use tools/ctx.py api.", task)
        self.assertIn("Backpass budget: 4321 tokens", task)
        self.assertIn("CLAUDE.md pointer to AGENTS.md", task)

    def test_gotcha_accept_appends_inside_section_and_leaves_claude_pointer(self):
        r = self.make_root(); self.prop(edit_file=GOTCHAS, rule="eda.x fails live.", target="api-map", kind="eda_api_failure")
        before = self.snapshot(r)
        res = L.decide("Ptest01", "accept", reviewer="tester")
        self.assertTrue(res["applied"])
        t = _r(os.path.join(r, GOTCHAS))
        self.assertIn("## Learned gotchas (human-approved)\n", t)
        self.assertIn("- eda.x fails live. <!-- learn:Ptest01 sessions=2 -->", t)
        self.assertTrue(t.startswith("# API\n\n## Calls\nx\n"))
        after = self.snapshot(r)
        self.assertEqual((after["AGENTS.md"], after["CLAUDE.md"]), (before["AGENTS.md"], before["CLAUDE.md"]))

    def test_regression_failure_reverts_and_leaves_claude_pointer(self):
        r = self.make_root(failing_test=True); self.prop(edit_file=GOTCHAS, rule="eda.x fails live.", target="api-map")
        before = self.snapshot(r)
        with self.assertRaises(DeskError) as cm:
            L.decide("Ptest01", "accept", reviewer="tester")
        self.assertIn("REVERTED", str(cm.exception))
        self.assertEqual(self.snapshot(r), before)
        self.assertFalse(os.path.exists(os.path.join(L.STATE, "decisions.jsonl")))

    def test_apply_rule_refuses_memory_files(self):
        r = self.make_root(); before = self.snapshot(r)
        for target in ("AGENTS.md", "CLAUDE.md"):
            with self.assertRaises(UsageError) as cm:
                L.apply_rule(self.prop(edit_file=target), run_tests=False)
            self.assertIn("backpass apply", str(cm.exception))
        self.assertEqual(self.snapshot(r), before)

    def test_diverged_claude_md_is_named_in_the_task(self):
        r = self.make_root(claude="# AGENTS\n\n## Never\n1. x\n"); self.prop(); before = self.snapshot(r)
        L.decide("Ptest01", "accept", reviewer="tester")
        self.assertIn("diverged from the pointer form", _r(os.path.join(L.STATE, "tasks", "Ptest01.md")))
        self.assertEqual(self.snapshot(r), before)

    def test_budget_read_from_backpassrc(self):
        self.make_root(budget=4321)
        with open(os.path.join(L.STATE, "config.json"), "w") as f: json.dump({"instruction_budget_tokens": 99}, f)
        self.assertEqual(L.cfg()["instruction_budget_tokens"], 4321)   # .backpassrc.json is the only source
        os.remove(os.path.join(L.ROOT, ".backpassrc.json"))
        self.assertEqual(L.cfg()["instruction_budget_tokens"], L.BACKPASS_DEFAULT_BUDGET)
        with open(os.path.join(L.ROOT, ".backpassrc.json"), "w") as f: json.dump({"budgetTokens": "big"}, f)
        with self.assertRaises(ConfigError):
            L.cfg()

    def test_repo_budget_matches_backpassrc(self):
        with open(os.path.join(ROOT, ".backpassrc.json"), encoding="utf-8") as f:
            self.assertEqual(L.backpass_budget(ROOT), json.load(f)["budgetTokens"])

    def test_protected_requires_engineering_review_and_never_edits(self):
        r = self.make_root(); self.prop(protected=True, files=["desk/spec.py"])
        with self.assertRaises(ApprovalRequired):
            L.decide("Ptest01", "accept", reviewer="tester")
        res = L.decide("Ptest01", "accept", reviewer="tester", engineering_review="lead")
        self.assertFalse(res["applied"]); self.assertIn("task", res)
        self.assertNotIn("learn:", _r(os.path.join(r, "AGENTS.md")))

    def test_unknown_proposal_is_a_usage_error(self):
        self.make_root(); self.prop()
        with self.assertRaises(UsageError):
            L.decide("Pnope", "accept", reviewer="tester")

    def test_protected_list_covers_engineering_rules(self):
        for f in ("desk/spec.py", "desk/erc.py", "desk/calc.py", "desk/release.py", "tools/verify.py", "docs/02_SCHEMATIC_STYLE.md"):
            self.assertIn(f, L.PROTECTED)


class TestSingleMemoryWriter(unittest.TestCase):
    """AGENTS.md section L: transcript-derived memory edits land only via `backpass apply`. No DESK module may open
    AGENTS.md or CLAUDE.md for writing, and the learn engine's editable surfaces exclude them."""
    WRITE_RX = re.compile(r"""(open\([^)]*['"][wax+]+['"]|write_text\(|write_bytes\(|os\.replace\(|shutil\.(copy|move))""")

    def test_no_code_writes_memory_files(self):
        offenders = []
        for sub in ("desk", "tools", "devtools"):
            for dp, _, files in os.walk(os.path.join(ROOT, sub)):
                for fn in files:
                    if not fn.endswith((".py", ".mjs", ".js")): continue
                    path = os.path.join(dp, fn)
                    with open(path, encoding="utf-8", errors="replace") as f:
                        for n, line in enumerate(f, 1):
                            if ("AGENTS.md" in line or "CLAUDE.md" in line) and self.WRITE_RX.search(line):
                                offenders.append(f"{os.path.relpath(path, ROOT)}:{n}: {line.strip()[:100]}")
        self.assertEqual(offenders, [], "\n".join(offenders))

    def test_editable_surfaces_exclude_memory_files(self):
        self.assertFalse(set(L.EDITABLE) & set(L.MEMORY_FILES))
        self.assertEqual(set(L.MEMORY_FILES), {"AGENTS.md", "CLAUDE.md"})


@unittest.skipUnless(shutil.which("node") and os.path.exists(os.path.join(L.DEFAULTS["backpass_dir"], "src", "redact.js")),
                     "node or Backpass missing (python tools/learn.py setup)")
class TestBackpassAdapter(Base):
    def test_pi_store_parsed_filtered_and_redacted(self):
        home = os.path.join(self.tmp, "home"); store = os.path.join(home, ".pi", "agent", "sessions", "--x--")
        os.makedirs(store)
        lines = [{"type": "session", "id": "s1", "cwd": ROOT, "timestamp": "2030-01-01T00:00:00Z"},
                 {"type": "message", "message": {"role": "user", "content": "build it, token ghp_" + "A" * 36}},
                 {"type": "message", "message": {"role": "assistant", "content": [{"type": "toolCall", "id": "t1", "name": "bash",
                                                                                   "arguments": {"command": "python tools/ctx.py P brief"}}]}},
                 {"type": "message", "message": {"role": "toolResult", "toolCallId": "t1", "content": [{"type": "text", "text": "# BRIEF"}]}}]
        with open(os.path.join(store, "s1.jsonl"), "w") as f:
            for l in lines: f.write(json.dumps(l) + "\n")
        other = os.path.join(home, ".pi", "agent", "sessions", "--y--"); os.makedirs(other)
        with open(os.path.join(other, "s2.jsonl"), "w") as f:
            f.write(json.dumps({"type": "session", "id": "s2", "cwd": "C:/elsewhere", "timestamp": "2030-01-01T00:00:00Z"}) + "\n")
        out, known = os.path.join(self.tmp, "o.jsonl"), os.path.join(self.tmp, "k.json")
        with open(known, "w") as f: f.write("{}")
        env = {**os.environ, "USERPROFILE": home, "HOME": home}
        p = subprocess.run(["node", os.path.join(ROOT, "desk", "learn", "collect.mjs"), L.DEFAULTS["backpass_dir"], out,
                            json.dumps([ROOT]), "36500", known], capture_output=True, text=True, env=env)
        self.assertEqual(p.returncode, 0, p.stderr)
        rows = [json.loads(l) for l in _r(out).splitlines() if l.strip()]
        self.assertEqual([r["id"] for r in rows], ["s1"])                     # s2 filtered (not under root, no DESK use)
        ev = rows[0]["events"]
        t = next(e for e in ev if e["kind"] == "tool")
        self.assertEqual((t["name"], t["result"]), ("bash", "# BRIEF"))       # Backpass folded the tool result
        self.assertNotIn("ghp_" + "A" * 36, json.dumps(rows))                  # Backpass redaction applied


if __name__ == "__main__":
    unittest.main()
