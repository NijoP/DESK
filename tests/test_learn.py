"""Learning Engine tests: detectors, corroboration, idempotence, era provenance, rejection memory, human gate,
protected surfaces, budget, regression revert, and a real Backpass-adapter integration test (skipped if node/backpass
are missing). Offline. Run: python -m unittest discover -s tests -v"""
import json, os, shutil, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from desk.learn import engine as L  # noqa: E402

BIG = "x" * 20000


def _r(p):
    with open(p, encoding="utf-8") as f: return f.read()


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


class TestHumanGate(Base):
    def make_root(self, failing_test=False):
        r = os.path.join(self.tmp, "repo"); os.makedirs(os.path.join(r, "tests"))
        with open(os.path.join(r, "AGENTS.md"), "w") as f: f.write("# AGENTS\n\n## Never\n1. x\n")
        with open(os.path.join(r, "CLAUDE.md"), "w") as f: f.write("# AGENTS\n")
        with open(os.path.join(r, "tests", "test_ok.py"), "w") as f:
            f.write("import unittest\nclass T(unittest.TestCase):\n    def test(self): self.assertTrue(" + ("False" if failing_test else "True") + ")\n")
        L.ROOT = r
        return r

    def prop(self, **kw):
        p = {"id": "Ptest01", "sig": "s", "kind": "reference_read", "n_sessions": 2, "occurrences": 2, "measured_tokens": 10,
             "edit_file": "AGENTS.md", "rule": "Use tools/ctx.py api.", "protected": False, "target": "context", "why": "w",
             "change": "c", "files": [], "evidence": [{"session": "pi:a", "model": "m", "event": "0", "quote": "q"}]}
        p.update(kw)
        with open(os.path.join(L.STATE, "proposals.json"), "w") as f: json.dump([p], f)
        return p

    def test_accept_appends_only_inside_section_with_provenance_and_mirrors(self):
        r = self.make_root(); self.prop()
        res = L.decide("Ptest01", "accept", reviewer="tester")
        self.assertTrue(res["applied"])
        t = _r(os.path.join(r, "AGENTS.md"))
        self.assertIn("## Learned rules (human-approved)\n", t)
        self.assertIn("- Use tools/ctx.py api. <!-- learn:Ptest01 sessions=2 -->", t)
        self.assertTrue(t.startswith("# AGENTS\n\n## Never\n1. x\n"))
        self.assertEqual(t, _r(os.path.join(r, "CLAUDE.md")))

    def test_regression_failure_reverts(self):
        r = self.make_root(failing_test=True); self.prop()
        with self.assertRaises(SystemExit):
            L.decide("Ptest01", "accept", reviewer="tester")
        self.assertEqual(_r(os.path.join(r, "AGENTS.md")), "# AGENTS\n\n## Never\n1. x\n")
        self.assertFalse(os.path.exists(os.path.join(L.STATE, "decisions.jsonl")))

    def test_protected_requires_engineering_review_and_never_edits(self):
        r = self.make_root(); self.prop(protected=True, files=["desk/spec.py"])
        with self.assertRaises(SystemExit):
            L.decide("Ptest01", "accept", reviewer="tester")
        res = L.decide("Ptest01", "accept", reviewer="tester", engineering_review="lead")
        self.assertFalse(res["applied"]); self.assertIn("task", res)
        self.assertNotIn("learn:", _r(os.path.join(r, "AGENTS.md")))

    def test_budget_enforced(self):
        self.make_root(); self.prop(rule="r" * 20000)
        with self.assertRaises(SystemExit) as cm:
            L.decide("Ptest01", "accept", reviewer="tester")
        self.assertIn("budget", str(cm.exception))

    def test_protected_list_covers_engineering_rules(self):
        for f in ("desk/spec.py", "desk/erc.py", "desk/calc.py", "desk/release.py", "tools/verify.py", "docs/02_SCHEMATIC_STYLE.md"):
            self.assertIn(f, L.PROTECTED)


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
