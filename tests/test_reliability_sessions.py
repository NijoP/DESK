"""Project identity and window binding (desk/reliability/project_isolation.py, desk/bridge.py).

Simulated with a fake gateway: three EasyEDA windows, two projects with similar names, window-id rotation, a gateway
restart, a project closing mid-operation, a stale cached session, a successful API response from the wrong document,
an unbound mutation, and two terminals on independent projects. No EasyEDA, no network.
"""
import io
import json
import os
import shutil
import tempfile
import threading
import unittest
import urllib.error
from unittest import mock

from desk import bridge, ops
from desk.errors import IdentityUnverified, BridgeWindowRotated, BridgeScriptError
from desk.reliability.models import HealthStatus
from desk.reliability.project_isolation import (ProjectSession, SessionResolver, WindowIdentity, PROJECT_INFO_JS, ACTIVE_DOC_JS,
                                                 is_window_disconnected_error, session_from_project)

UPS = "41d5060e3af143dfbfbbc17bb1afb243"
LIGHT = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"
UPS_PCB, UPS_SCH, LIGHT_PCB = "ups-pcb-uuid", "ups-sch-uuid", "light-pcb-uuid"


class FakeGateway:
    """windows: {window_id: (project_uuid, project_name, active_document_uuid)}"""

    def __init__(self, windows, active=None):
        self.win = dict(windows)
        self.active = active
        self.calls = []

    def windows(self):
        return [{"windowId": w, "active": w == self.active} for w in self.win]

    def execute(self, window_id, code, timeout=5.0):
        self.calls.append((window_id, code[:40]))
        wid = window_id or self.active
        if wid not in self.win:
            return {"success": False, "error": f"EDA window {window_id} is no longer connected"}
        puid, name, doc = self.win[wid]
        if code == PROJECT_INFO_JS:
            return {"success": True, "result": {"project_uuid": puid, "project_name": name, "document_uuid": doc, "document_type": "pcb"}}
        if code == ACTIVE_DOC_JS:
            return {"success": True, "result": doc}
        return {"success": True, "result": True}

    def rotate(self):
        """A gateway reconnect: every id changes, projects stay."""
        self.win = {f"r-{w}": v for w, v in self.win.items()}
        if self.active:
            self.active = f"r-{self.active}"


def three_windows():
    return FakeGateway({"671ec3d9": (UPS, "ups claude test", UPS_PCB), "10b1d581": (LIGHT, "light", LIGHT_PCB),
                        "22aa33bb": (LIGHT + "x", "light (copy)", "other-doc")}, active="10b1d581")


def ups_session(window_id=None):
    return ProjectSession(project_id="UPS_1000", project_path="projects/UPS_1000", project_uuid=UPS, schematic_uuid=UPS_SCH,
                         pcb_uuid=UPS_PCB, window_id=window_id)


class ResolverBinding(unittest.TestCase):
    def test_binds_to_the_window_hosting_the_project_uuid_not_the_active_one(self):
        gw = three_windows()
        s = SessionResolver(gw).resolve(ups_session())
        self.assertEqual(s.window_id, "671ec3d9")           # not the active window 10b1d581 (project light)
        self.assertEqual(s.health_status, HealthStatus.HEALTHY)
        self.assertEqual(s.session_generation, 1)

    def test_similar_names_do_not_match(self):
        gw = FakeGateway({"w1": (LIGHT, "light", LIGHT_PCB), "w2": (LIGHT + "x", "light", "doc2")})
        s = SessionResolver(gw).resolve(ProjectSession("LIGHT", "projects/LIGHT", project_uuid=LIGHT + "x"))
        self.assertEqual(s.window_id, "w2")

    def test_two_windows_same_project_refuse(self):
        gw = FakeGateway({"w1": (UPS, "ups", UPS_PCB), "w2": (UPS, "ups", UPS_SCH)})
        with self.assertRaises(IdentityUnverified) as cm:
            SessionResolver(gw).resolve(ups_session())
        self.assertIn("2 EasyEDA window(s)", str(cm.exception))
        self.assertEqual(sorted(cm.exception.context["candidates"]), ["w1", "w2"])

    def test_no_window_refuses_and_marks_disconnected(self):
        gw = FakeGateway({"w1": (LIGHT, "light", LIGHT_PCB)})
        s = ups_session("stale")
        with self.assertRaises(IdentityUnverified):
            SessionResolver(gw).resolve(s)
        self.assertEqual(s.health_status, HealthStatus.DISCONNECTED)

    def test_unknown_identity_refuses(self):
        with self.assertRaises(IdentityUnverified):
            SessionResolver(three_windows()).resolve(ProjectSession("X", "projects/X"))

    def test_document_fallback_when_project_uuid_unknown(self):
        gw = three_windows()
        s = SessionResolver(gw).resolve(ProjectSession("UPS_1000", "p", pcb_uuid=UPS_PCB))
        self.assertEqual(s.window_id, "671ec3d9")
        self.assertEqual(s.project_uuid, UPS)             # learned from the window

    def test_gateway_restart_is_a_refusal_not_a_guess(self):
        class Down:
            def windows(self):
                raise OSError("connection refused")

            def execute(self, *a, **k):
                raise OSError("connection refused")
        s = ups_session("671ec3d9")
        with self.assertRaises(IdentityUnverified) as cm:
            SessionResolver(Down()).resolve(s)
        self.assertIn("gateway unreachable", str(cm.exception))
        self.assertEqual(s.health_status, HealthStatus.DISCONNECTED)


class Rotation(unittest.TestCase):
    def test_rotation_rebinds_when_unambiguous_and_bumps_generation(self):
        gw = three_windows()
        r = SessionResolver(gw)
        s = r.resolve(ups_session())
        gw.rotate()
        with self.assertRaises(BridgeWindowRotated):
            r.verify_target(s, UPS_PCB)
        self.assertIsNone(s.window_id)
        s = r.rebind_after_rotation(s)
        self.assertEqual(s.window_id, "r-671ec3d9")
        self.assertEqual(s.window_generation, 2)
        self.assertTrue(any("rotated" in n for n in s.notes))
        self.assertTrue(r.verify_target(s, UPS_PCB))

    def test_rotation_with_duplicate_project_refuses(self):
        gw = three_windows()
        r = SessionResolver(gw)
        s = r.resolve(ups_session())
        gw.rotate()
        gw.win["dup"] = (UPS, "ups claude test", UPS_SCH)
        with self.assertRaises(IdentityUnverified):
            r.rebind_after_rotation(s)
        self.assertFalse(s.bound)

    def test_project_closed_during_operation(self):
        gw = three_windows()
        r = SessionResolver(gw)
        s = r.resolve(ups_session())
        del gw.win["671ec3d9"]
        with self.assertRaises(BridgeWindowRotated):
            r.verify_target(s, UPS_PCB)
        with self.assertRaises(IdentityUnverified):
            r.rebind_after_rotation(s)

    def test_disconnected_error_texts(self):
        self.assertTrue(is_window_disconnected_error("EDA window 7b1fb5fd is no longer connected"))
        self.assertTrue(is_window_disconnected_error("unknown window id"))
        self.assertFalse(is_window_disconnected_error("TypeError: x is not a function"))


class WrongDocument(unittest.TestCase):
    def test_success_from_the_wrong_document_fails_verify_target(self):
        gw = three_windows()
        r = SessionResolver(gw)
        s = r.resolve(ups_session())
        gw.win["671ec3d9"] = (UPS, "ups claude test", UPS_SCH)     # the user switched to the schematic tab
        self.assertFalse(r.verify_target(s, UPS_PCB))               # a `true` from this window would be the wrong document
        self.assertEqual(s.bound_document_uuid, UPS_SCH)
        self.assertEqual(s.health_status, HealthStatus.UNVERIFIED)


# ---------------------------------------------------------------------------------------------- desk.bridge.ex
class _Resp:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def read(self):
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class BridgeBinding(unittest.TestCase):
    """desk.bridge.ex against a fake gateway reached through urllib."""

    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="desk_rel_")
        self.proj = os.path.join(self.d, "UPS_1000")
        os.makedirs(self.proj)
        self.gw = three_windows()
        bridge.SessionRegistry._sessions.clear()
        from desk.reliability.circuit_breaker import BreakerRegistry
        BreakerRegistry.reset()
        self._env = dict(os.environ)
        os.environ["EDA_PORT"] = "49999"
        os.environ.pop("EDA_WINDOW_ID", None)
        os.environ.pop("DESK_ALLOW_UNBOUND_WINDOW", None)
        self.pj = os.path.join(self.proj, "project.json")

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)
        bridge.SessionRegistry._sessions.clear()
        shutil.rmtree(self.d, ignore_errors=True)

    def _write_pj(self, **extra):
        with open(self.pj, "w", encoding="utf-8") as f:
            json.dump({"name": "UPS_1000", "project_uuid": UPS, "pcb_uuid": UPS_PCB, "sheet_uuid": UPS_SCH, **extra}, f)

    def _urlopen(self, req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if url.endswith("/eda-windows"):
            return _Resp({"windows": self.gw.windows(), "activeWindowId": self.gw.active})
        body = json.loads(req.data.decode("utf-8"))
        env = self.gw.execute(body.get("windowId"), body["code"], timeout or 5.0)
        if not env.get("success") and "no longer connected" in str(env.get("error")):
            raise urllib.error.HTTPError(url, 500, "err", {}, io.BytesIO(json.dumps(env).encode("utf-8")))
        return _Resp(env)

    def test_unbound_mutation_is_refused(self):
        with mock.patch.object(bridge.urllib.request, "urlopen", side_effect=self._urlopen):
            with self.assertRaises(IdentityUnverified) as cm:
                bridge.ex("await eda.pcb_PrimitiveLine.delete(['x']); return true;")
        self.assertIn("no verified EasyEDA window binding", str(cm.exception))
        self.assertEqual(self.gw.calls, [])                          # nothing reached the gateway

    def test_unbound_read_still_runs_in_the_active_window(self):
        with mock.patch.object(bridge.urllib.request, "urlopen", side_effect=self._urlopen):
            r = bridge.ex("return 1;")
        self.assertTrue(r)
        self.assertEqual(self.gw.calls[-1][0], None)

    def test_project_uuid_scan_binds_mutation_to_the_right_window(self):
        self._write_pj()
        with mock.patch.object(bridge.urllib.request, "urlopen", side_effect=self._urlopen):
            r = bridge.ex("await eda.pcb_Document.save(); return true;", project_path=self.proj, is_mutation=True)
        self.assertTrue(r)
        self.assertEqual(self.gw.calls[-1][0], "671ec3d9")
        self.assertEqual(json.load(open(self.pj))["window_id"], "671ec3d9")   # persisted for the next tool

    def test_stale_cached_window_id_is_rebound_by_uuid_before_resend(self):
        self._write_pj(window_id="deadbeef")                        # from a previous gateway connection
        with mock.patch.object(bridge.urllib.request, "urlopen", side_effect=self._urlopen):
            r = bridge.ex("await eda.pcb_Document.save(); return true;", project_path=self.proj, is_mutation=True)
        self.assertTrue(r)
        sends = [c[0] for c in self.gw.calls if c[1].startswith("await eda.pcb_Document.save")]
        self.assertEqual(sends, ["deadbeef", "671ec3d9"])           # the gateway refused the stale id (not executed), then one resend
        self.assertEqual([w for w in sends if w in self.gw.win], ["671ec3d9"])   # only the rebound window executed it
        self.assertEqual(json.load(open(self.pj))["window_id"], "671ec3d9")
        s = bridge.SessionRegistry.get_session(self.proj)
        self.assertEqual(s.window_generation, 1)
        self.assertEqual(s.rotations[0]["from"], "deadbeef")

    def test_stale_id_with_ambiguous_project_refuses(self):
        self._write_pj(window_id="deadbeef")
        self.gw.win["dup"] = (UPS, "ups claude test", UPS_SCH)
        with mock.patch.object(bridge.urllib.request, "urlopen", side_effect=self._urlopen):
            with self.assertRaises(IdentityUnverified):
                bridge.ex("await eda.pcb_Document.save(); return true;", project_path=self.proj, is_mutation=True)
        self.assertFalse(any(c[1].startswith("await eda.pcb_Document.save") and c[0] in self.gw.win for c in self.gw.calls))

    def test_explicit_unbound_override_is_honoured_and_visible(self):
        with mock.patch.object(bridge.urllib.request, "urlopen", side_effect=self._urlopen):
            bridge.ex("await eda.pcb_Document.save(); return true;", allow_unbound=True)
        self.assertEqual(self.gw.calls[-1][0], None)


class TwoTerminalsTwoProjects(unittest.TestCase):
    def test_independent_projects_progress_concurrently_and_one_project_is_single_writer(self):
        d = tempfile.mkdtemp(prefix="desk_two_")
        a, b = os.path.join(d, "A"), os.path.join(d, "B")
        os.makedirs(a)
        os.makedirs(b)
        started, release = threading.Event(), threading.Event()

        def hold(project):
            with ops.write_op(project, "route", "PCB", window_id="w1", document_uuid="docA"):
                started.set()
                release.wait(5)

        t = threading.Thread(target=hold, args=(a,))
        t.start()
        self.assertTrue(started.wait(5))
        with ops.write_op(b, "route", "PCB", window_id="w2", document_uuid="docB"):   # B is not blocked by A
            pass
        with self.assertRaises(ops.WriteLockHeld):                                   # a second writer on A is
            with ops.write_op(a, "build", "01", force_unlock=False):
                pass
        release.set()
        t.join(5)
        begin = [r for r in ops.journal(a) if r["phase"] == "begin"][0]
        self.assertEqual((begin["window_id"], begin["document_uuid"]), ("w1", "docA"))
        shutil.rmtree(d, ignore_errors=True)


class SessionFromProject(unittest.TestCase):
    def test_fields(self):
        s = session_from_project("projects/UPS_1000", {"name": "UPS_1000", "project_uuid": UPS, "pcb_uuid": UPS_PCB, "sheet_uuid": UPS_SCH, "window_id": "x"})
        self.assertEqual((s.project_uuid, s.pcb_uuid, s.schematic_uuid, s.window_id), (UPS, UPS_PCB, UPS_SCH, "x"))
        self.assertEqual(s.documents(), (UPS_PCB, UPS_SCH))
        self.assertFalse(s.bound)                                   # a stored id is not a verified binding


if __name__ == "__main__":
    unittest.main()
