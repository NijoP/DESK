"""Roadmap increment I-0 "Truth first": one regression test per false-success finding.

Each test is the finding's reproduction from the 2026-11-21 repository audit, turned around: the reproduction used to
report success it had not earned; it must now fail closed. No bridge, no network, no EasyEDA.

F-1 verify passes vacuously        F-2 lint skipped through a block alias      F-4 dashboard "M3 passed" on any attempt
F-5 quality gates PASS w/o evidence F-8 is in test_mutation_policy.py          F-9 stale-lock reclaim deletes a fresh lock
F-10 live holder judged recycled    F-11 mutation resent after connection reset F-12 mutators missed by looks_mutating
F-13 rotated window -> None         S-1 cross-site / state-changing GET         S-2 unauthenticated POST /api/events
"""
import ast
import http.client
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")

from desk import bridge, netcheck, ops  # noqa: E402
from desk import spec as S  # noqa: E402
from desk.errors import BridgeMutationOutcomeUnknown, BridgeScriptError, WriteLockHeld  # noqa: E402
from desk.profile import DesignProfile  # noqa: E402
from desk.quality import QualityGateEvaluator, VerificationEvidence  # noqa: E402


def _block(bid, ref="U1", mpn="NOT_A_REAL_MPN_TRUTH_FIRST"):
    return {"id": bid, "title": bid, "parts": [{"ref": ref, "mpn": mpn, "pins": {"1": "GND"}}]}


def _project(tmp, blocks):
    proj = os.path.join(tmp, "P")
    os.makedirs(os.path.join(proj, "blocks"))
    for fname, b in blocks.items():
        with open(os.path.join(proj, "blocks", fname), "w", encoding="utf-8") as f:
            json.dump(b, f)
    return proj


# Runs a tools/ script in a child interpreter with the bridge replaced by a fake: the script's own module-level code
# (and _common's stdout/exit wrapping) never touches this test process. Prints the number of bridge calls.
_DRIVER = r'''
import json, runpy, sys
root, script, snap = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])
sys.path[:0] = [root, root + "/tools"]   # repo root first: tools/desk.py must not shadow desk/
import desk.bridge as B
calls = []
def fake_ex(code, **kw):
    calls.append(code[-80:])
    return snap
B.ex = fake_ex
B.load_project = lambda p: {"sheet_uuid": "SHEET"}
sys.argv = [script] + sys.argv[4:]
code = 0
try:
    runpy.run_path(script, run_name="__main__")
except SystemExit as e:
    code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    if not isinstance(e.code, int) and e.code is not None:
        print("EXIT:", e.code)
print("BRIDGE_CALLS=" + json.dumps(len(calls)))
sys.exit(code)
'''


def _run_tool(script, args, snap):
    env = dict(os.environ, DESK_TELEMETRY="0", PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, "-c", _DRIVER, ROOT, os.path.join(TOOLS, script), json.dumps(snap), *args],
                          capture_output=True, text=True, timeout=120, env=env, cwd=ROOT)


class F1VerifyIsNeverVacuous(unittest.TestCase):
    BLOCKS = [_block("PWR")]

    def test_unknown_block_id_is_an_error_not_an_empty_pass(self):
        E, _, _ = netcheck.compare(self.BLOCKS, {"TYPO"}, [], {})
        self.assertTrue(any("TYPO" in e and "not in the block specs" in e for e in E), E)

    def test_empty_id_set_is_an_error(self):
        E, _, _ = netcheck.compare(self.BLOCKS, set(), [], {})
        self.assertTrue(any("nothing was verified" in e for e in E), E)

    def test_known_id_still_compares(self):
        E, _, _ = netcheck.compare(self.BLOCKS, {"PWR"}, [], {})
        self.assertIn("PWR: U1 missing on sheet", E)

    def test_verify_cli_typo_and_no_layout_exit_nonzero_without_verified(self):
        tmp = tempfile.mkdtemp()
        try:
            proj = _project(tmp, {"01_PWR.json": _block("PWR")})
            empty_sheet = {"nl": "", "parts": []}
            for args in ([proj, "TYPO"], [proj]):                # misspelled id; no layout.json and no id
                r = _run_tool("verify.py", args, empty_sheet)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertNotIn("\nVERIFIED", "\n" + r.stdout)
                self.assertIn("FAIL", r.stdout)
            r = _run_tool("verify.py", [proj, "01"], empty_sheet)  # an alias resolves and really compares
            self.assertEqual(r.returncode, 1)
            self.assertIn("PWR: U1 missing on sheet", r.stdout)
            ledger = os.path.join(proj, "LEDGER.jsonl")
            if os.path.exists(ledger):
                with open(ledger, encoding="utf-8") as f:
                    self.assertNotIn('"verified"', f.read())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class F2LintFollowsTheResolvedBlock(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.proj = _project(self.tmp, {"02_X.json": _block("X")})   # mpn not in the library -> lint error

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_alias_lints_the_block_it_names(self):
        E_id, _ = S.lint(self.proj, "X")
        self.assertTrue(E_id)
        for alias in ("02", "02_X", "02_X.json"):
            E, _ = S.lint(self.proj, alias)
            self.assertEqual(E, E_id, alias)

    def test_unknown_block_is_a_lint_error(self):
        E, _ = S.lint(self.proj, "NOPE")
        self.assertTrue(any("'NOPE' not found" in e for e in E), E)

    def test_build_by_alias_stops_on_lint_before_any_bridge_call(self):
        r = _run_tool("build.py", [self.proj, "02"], {"W": 1, "H": 1, "REF": []})
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("lint failed", r.stdout + r.stderr)
        self.assertIn("BRIDGE_CALLS=0", r.stdout)


class F4RoutingStageNeedsTheConnectivityVerdict(unittest.TestCase):
    def setUp(self):
        from desk.runtime.events import EventBus
        from desk.runtime.projection import ExecutionProjection
        self.tmp = tempfile.mkdtemp()
        self.proj = os.path.join(self.tmp, "route_proj")
        os.makedirs(os.path.join(self.proj, "state", "route"))
        self.projection = ExecutionProjection(project_id=self.proj, event_bus=EventBus())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _stage_after(self, record, ses=False):
        from desk.runtime import projection as PJ
        if record is not None:
            with open(os.path.join(self.proj, "state", "route", "routing_attempt.json"), "w") as f:
                json.dump(record, f)
        if ses:
            with open(os.path.join(self.proj, "state", "route", "desk_route.ses"), "w") as f:
                f.write("(session x)")
        with mock.patch.object(PJ, "_scan_active_engineering_processes", return_value=[]):
            self.projection.reconcile_live_telemetry(self.proj)
        return self.projection.stages[PJ.STAGE_PCB_ROUTING]

    def test_failed_attempt_and_ses_file_are_not_m3_passed(self):
        # Reproduction: pipeline.py writes routing_attempt.json on every attempt, failed imports included.
        st = self._stage_after({"import_success": False, "fully_connected_nets": 36, "total_nets": 106,
                                "routing_verdict": "PARTIAL"}, ses=True)
        self.assertNotEqual(st.status, "COMPLETED")
        self.assertNotIn("M3 passed", st.output_summary or "")

    def test_legacy_record_without_verdict_is_not_m3_passed(self):
        st = self._stage_after({"import_success": True, "fully_connected_nets": 10, "populated_nets": 10}, ses=True)
        self.assertNotEqual(st.status, "COMPLETED")

    def test_full_readback_verdict_passes_m3(self):
        st = self._stage_after({"routing_verdict": "FULL", "fully_connected_nets": 40, "total_nets": 40})
        self.assertEqual(st.status, "COMPLETED")
        self.assertIn("40/40", st.output_summary)


class F5QualityGatesNeedEvidence(unittest.TestCase):
    def test_no_profile_means_unknown_not_pass(self):
        # Reproduction: evaluate(drc_violations=[], unconnected_nets=[], discontinuities_count=0) was approved.
        rep = QualityGateEvaluator.evaluate(drc_violations=[], unconnected_nets=[], discontinuities_count=0)
        self.assertFalse(rep.approved)
        for g in ("valid_stackup", "electrical_constraints_met", "manufacturing_constraints_met"):
            self.assertEqual(getattr(rep.hard_gates, g).state, "UNKNOWN", g)

    def test_explicit_opt_out_keeps_old_behaviour(self):
        rep = QualityGateEvaluator.evaluate(drc_violations=[], unconnected_nets=[], discontinuities_count=0,
                                            require_profile=False)
        self.assertTrue(rep.approved)

    def test_evidence_for_another_revision_is_stale(self):
        prof = DesignProfile(project_id="T")
        ev = VerificationEvidence(evidence_id="EV1", timestamp=1.0, pcb_revision_hash="REV_OLD",
                                  profile_hash=prof.profile_hash, tool_and_version="drc", status="PASS")
        rep = QualityGateEvaluator.evaluate(drc_violations=[], unconnected_nets=[], discontinuities_count=0,
                                            profile=prof, board_revision="REV_NEW", evidence_map={"zero_shorts": ev})
        self.assertEqual(rep.hard_gates.zero_shorts.state, "STALE")
        self.assertFalse(rep.approved)
        self.assertEqual(ev.status, "PASS")                      # the caller's record is not modified

    def test_readiness_with_no_evidence_is_not_ready(self):
        from desk.rework.readiness import ManufacturingReadinessEngine, ReadinessOutcome
        from desk.snapshot import IndexedPCBSnapshot
        tmp = tempfile.mkdtemp()
        try:
            a = ManufacturingReadinessEngine.evaluate(session_id="s", project_path=tmp,
                                                      snapshot=IndexedPCBSnapshot(raw_dump={}, project_id="T"))
            self.assertEqual(a.outcome, ReadinessOutcome.NOT_READY)
            self.assertFalse(a.hard_gates_passed)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class F9StaleLockReclaimRace(unittest.TestCase):
    def test_fresh_lock_taken_during_reclaim_survives_and_only_one_holder_remains(self):
        tmp = tempfile.mkdtemp()
        lock = os.path.join(tmp, "write.lock")
        try:
            with open(lock, "w") as f:
                json.dump({"id": "dead", "pid": 9999999, "ts": time.time() - 10}, f)
            fresh = {"id": "fresh_B", "pid": os.getpid(), "ts": time.time(),
                     "pid_start_time": ops.get_process_start_time(os.getpid()), "op": "build", "target": "B"}
            real_alive = ops.is_process_alive

            def racing_alive(pid):
                # While writer A judges the dead holder, writer B reclaims it and takes a fresh lock.
                if pid == 9999999 and not os.path.exists(lock + ".b_done"):
                    os.remove(lock)
                    with open(lock, "w") as f:
                        json.dump(fresh, f)
                    open(lock + ".b_done", "w").close()
                return real_alive(pid)

            with mock.patch.object(ops, "is_process_alive", side_effect=racing_alive):
                with self.assertRaises(WriteLockHeld):
                    ops.acquire_atomic_lock(lock, {"id": "A", "pid": os.getpid(), "ts": time.time()}, ttl=600)
            with open(lock) as f:
                self.assertEqual(json.load(f)["id"], "fresh_B")       # B still holds it; A never got in
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_dead_holder_is_still_reclaimed(self):
        tmp = tempfile.mkdtemp()
        lock = os.path.join(tmp, "write.lock")
        try:
            with open(lock, "w") as f:
                json.dump({"id": "dead", "pid": 9999999, "ts": time.time() - 3600}, f)
            ops.acquire_atomic_lock(lock, {"id": "A", "pid": os.getpid(), "ts": time.time()}, ttl=10)
            with open(lock) as f:
                self.assertEqual(json.load(f)["id"], "A")
            self.assertFalse(os.path.exists(lock + ".reclaim"))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


@unittest.skipUnless(os.path.isdir("/proc") and os.name != "nt", "procfs start-time path (Linux)")
class F10ProcessStartTime(unittest.TestCase):
    def setUp(self):
        self.t_spawn = time.time()
        self.child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        time.sleep(2.0)                                       # nobody has looked at /proc/<pid> yet

    def tearDown(self):
        self.child.kill()
        self.child.wait()

    def test_start_time_is_the_real_process_start_not_first_access(self):
        t = ops.get_process_start_time(self.child.pid)
        self.assertIsNotNone(t)
        # btime is whole seconds, so the value may be up to 1 s early; the dentry time was ~2 s late here.
        self.assertGreater(t, self.t_spawn - 1.5)
        self.assertLess(t, self.t_spawn + 0.7)
        self.assertEqual(t, ops.get_process_start_time(self.child.pid))   # stable for the same process

    def test_live_holder_is_not_reclaimed_as_recycled(self):
        tmp = tempfile.mkdtemp()
        lock = os.path.join(tmp, "write.lock")
        try:
            holder = {"id": "live", "pid": self.child.pid, "ts": self.t_spawn,
                      "pid_start_time": ops.get_process_start_time(self.child.pid), "op": "build", "target": "X"}
            with open(lock, "w") as f:
                json.dump(holder, f)
            with self.assertRaises(WriteLockHeld):
                ops.acquire_atomic_lock(lock, {"id": "A", "pid": os.getpid(), "ts": time.time()}, ttl=600)
            # ...but a recorded start time that does not match the live PID is a recycled PID.
            holder["pid_start_time"] -= 100.0
            with open(lock, "w") as f:
                json.dump(holder, f)
            ops.acquire_atomic_lock(lock, {"id": "A", "pid": os.getpid(), "ts": time.time()}, ttl=600)
            with open(lock) as f:
                self.assertEqual(json.load(f)["id"], "A")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class _Resp:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class BridgeCase(unittest.TestCase):
    MUTATION = "await eda.pcb_PrimitiveVia.create('GND', 0, 0, 12, 24); return true;"

    def setUp(self):
        from desk.reliability.circuit_breaker import BreakerRegistry
        bridge.SessionRegistry._sessions.clear()
        BreakerRegistry.reset()
        self._env = dict(os.environ)
        os.environ["EDA_PORT"] = "49999"
        os.environ.pop("DESK_ALLOW_UNBOUND_WINDOW", None)
        self.sleep = mock.patch.object(bridge.time, "sleep")
        self.sleep.start()

    def tearDown(self):
        self.sleep.stop()
        os.environ.clear()
        os.environ.update(self._env)
        bridge.SessionRegistry._sessions.clear()


class F11NoResendAfterDelivery(BridgeCase):
    def _sends(self, exc, code, **kw):
        calls = []

        def urlopen(req, timeout=None):
            calls.append(req.full_url)
            if len(calls) == 1:
                raise exc
            return _Resp({"success": True, "result": "second"})

        with mock.patch.object(bridge.urllib.request, "urlopen", side_effect=urlopen):
            try:
                return bridge.ex(code, window_id="W1", retries=1, **kw), calls
            except BridgeMutationOutcomeUnknown as e:
                return e, calls

    def test_connection_reset_after_send_raises_instead_of_resending(self):
        for exc in (urllib.error.URLError(ConnectionResetError(104, "reset")),
                    http.client.RemoteDisconnected("Remote end closed connection without response"),
                    ConnectionResetError(104, "reset")):
            res, calls = self._sends(exc, self.MUTATION)
            self.assertIsInstance(res, BridgeMutationOutcomeUnknown, exc)
            self.assertTrue(res.possibly_mutated)
            self.assertEqual(len(calls), 1, exc)                 # sent exactly once

    def test_refused_connection_never_reached_the_gateway_and_is_retried(self):
        res, calls = self._sends(urllib.error.URLError(ConnectionRefusedError(111, "refused")), self.MUTATION)
        self.assertEqual((res, len(calls)), ("second", 2))

    def test_read_only_script_is_still_retried_after_reset(self):
        res, calls = self._sends(urllib.error.URLError(ConnectionResetError(104, "reset")), "return 1;")
        self.assertEqual((res, len(calls)), ("second", 2))


class F12MutatorDetection(unittest.TestCase):
    def test_rule_and_flag_mutators_are_mutating(self):
        for js in ("await eda.pcb_Drc.createNetClass('HV', ['VP'], 'red');",
                   "await eda.pcb_Drc.deleteNetClass('HV');",
                   "await eda.pcb_Drc.createDifferentialPair('USB', 'DP', 'DN');",
                   "pin.setState_NoConnected(true);"):
            self.assertTrue(bridge.looks_mutating(js), js)

    def test_reads_are_not_mutating(self):
        for js in ("return await eda.pcb_PrimitiveComponent.getAll();",
                   "const nl = await eda.sch_Netlist.getNetlist('Protel2'); return nl;"):
            self.assertFalse(bridge.looks_mutating(js), js)


class F13RotatedWindowNeverReturnsNone(BridgeCase):
    def test_rebind_on_the_last_attempt_still_resends(self):
        replies = [{"success": False, "error": "window W1 is no longer connected"}, {"success": True, "result": 42}]
        sent = []

        def urlopen(req, timeout=None):
            sent.append(json.loads(req.data.decode("utf-8")).get("windowId"))
            return _Resp(replies.pop(0))

        with mock.patch.object(bridge.urllib.request, "urlopen", side_effect=urlopen), \
             mock.patch.object(bridge, "rebind_session", return_value="W2"):
            res = bridge.ex(self.MUTATION, window_id="W1", retries=0)
        self.assertEqual(res, 42)
        self.assertEqual(sent, ["W1", "W2"])

    def test_second_rotation_is_an_error_not_none(self):
        def urlopen(req, timeout=None):
            return _Resp({"success": False, "error": "window is no longer connected"})

        with mock.patch.object(bridge.urllib.request, "urlopen", side_effect=urlopen), \
             mock.patch.object(bridge, "rebind_session", return_value="W2"):
            with self.assertRaises(BridgeScriptError):
                bridge.ex(self.MUTATION, window_id="W1", retries=0)


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class DashboardSecurity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from desk.runtime.server import DeskServer
        cls.server = DeskServer(host="127.0.0.1", port=_free_port())
        cls.url, cls.port = cls.server.start(background=True)
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def _raw(self, request: bytes) -> int:
        with socket.create_connection(("127.0.0.1", self.port), timeout=3) as s:
            s.sendall(request)
            data = b""
            while b"\r\n" not in data:
                chunk = s.recv(1024)
                if not chunk:
                    break
                data += chunk
        return int(data.split(b" ", 2)[1])

    def _req(self, path, method="GET", headers=None, data=None):
        req = urllib.request.Request(self.url + path, data=data, method=method, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=3) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code

    # S-1 -------------------------------------------------------------------------------------------------------
    def test_request_without_host_or_origin_is_forbidden(self):
        self.assertEqual(self._raw(b"GET /api/v1/health HTTP/1.0\r\n\r\n"), 403)

    def test_other_local_port_origin_is_forbidden(self):
        other = self.port + 1
        self.assertEqual(self._req("/api/v1/health", headers={"Origin": f"http://localhost:{other}"}), 403)
        self.assertEqual(self._raw(f"GET /api/v1/health HTTP/1.1\r\nHost: 127.0.0.1:{other}\r\n\r\n".encode()), 403)

    def test_same_origin_read_still_works(self):
        self.assertEqual(self._req("/api/v1/health"), 200)
        self.assertEqual(self._req("/api/v1/health", headers={"Origin": f"http://127.0.0.1:{self.port}"}), 200)

    def test_state_changing_get_needs_the_token(self):
        tmp = tempfile.mkdtemp()
        try:
            target = os.path.join(tmp, "victim")
            os.makedirs(target)
            for p in ("/api/project/select?project=", "/api/v1/sync?project="):
                self.assertEqual(self._req(p + urllib.request.quote(target)), 403, p)
            self.assertFalse(os.path.exists(os.path.join(target, "state", "execution_state.json")))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    # S-2 -------------------------------------------------------------------------------------------------------
    def test_post_events_without_token_cannot_forge_acceptance(self):
        from desk.runtime.events import get_event_bus
        bus = get_event_bus()
        before = len(bus.get_events_since(None, limit=500))
        body = json.dumps({"event_type": "stage.complete", "stage": "pcb_routing", "message": "forged"}).encode()
        self.assertEqual(self._req("/api/events", "POST", {"Content-Type": "application/json"}, body), 403)
        self.assertEqual(self._req("/api/events", "POST", {"X-DESK-Token": "guess"}, body), 403)
        self.assertEqual(len(bus.get_events_since(None, limit=500)), before)

    def test_post_events_with_the_launch_token_is_accepted(self):
        body = json.dumps({"event_type": "test.truth_first.ping", "message": "ok"}).encode()
        self.assertEqual(self._req("/api/events", "POST", {"X-DESK-Token": self.server.token}, body), 200)

    def test_dead_read_only_do_post_is_gone(self):
        from desk.runtime import server as srv
        with open(srv.__file__, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "DeskRequestHandler")
        self.assertEqual(sum(1 for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "do_POST"), 1)


if __name__ == "__main__":
    unittest.main()
