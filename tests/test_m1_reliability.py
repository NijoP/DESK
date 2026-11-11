"""Milestone-1 reliability fixes: lock reclaim race, atomic writes, dirty-on-timeout,
fail-closed readiness flags, capability registry, doctor."""
import json
import os
import shutil
import tempfile
import threading
import time
import unittest
from unittest import mock

from desk import ops
from desk.fsutil import atomic_write_json, read_json
from desk.ops import acquire_atomic_lock, write_op, OP_NON_IDEMPOTENT_MUTATION


class TestLockReclaimRace(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="desk_lock_")
        self.lock = os.path.join(self.d, "write.lock")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_unreadable_young_lock_is_treated_as_held(self):
        # Simulate the window between O_EXCL create and the record write: an empty lock file.
        open(self.lock, "w").close()
        rec = {"id": "b", "pid": os.getpid(), "ts": time.time(), "op": "t", "target": "T"}
        t0 = time.time()
        with self.assertRaises(SystemExit):
            # 40 attempts x 50 ms grace loop, then the empty record is finally judged stale only
            # after LOCK_WRITE_GRACE_SEC; to keep the test fast, pin the grace window to 0.3 s.
            with mock.patch.object(ops, "LOCK_WRITE_GRACE_SEC", 0.3):
                # Freshen the file continuously so it never ages past the grace window.
                stop = threading.Event()

                def toucher():
                    while not stop.is_set():
                        os.utime(self.lock, None)
                        time.sleep(0.02)

                th = threading.Thread(target=toucher, daemon=True)
                th.start()
                try:
                    acquire_atomic_lock(self.lock, rec, ttl=10)
                finally:
                    stop.set()
                    th.join()
        self.assertGreater(time.time() - t0, 0.3)
        # The original (empty) lock was never reclaimed by us.
        self.assertEqual(os.path.getsize(self.lock), 0)

    def test_two_threads_exactly_one_holder(self):
        winners = []
        errors = []
        barrier = threading.Barrier(2)

        def contend(name):
            rec = {"id": name, "pid": os.getpid(), "ts": time.time(), "op": "t", "target": "T"}
            barrier.wait()
            try:
                acquire_atomic_lock(self.lock, rec, ttl=10)
                winners.append(name)
            except SystemExit as e:
                errors.append(str(e))

        ts = [threading.Thread(target=contend, args=(n,)) for n in ("A", "B")]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        self.assertEqual(len(winners), 1, (winners, errors))
        self.assertEqual(len(errors), 1)


class TestAtomicWrite(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="desk_fs_")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_crash_mid_write_keeps_original(self):
        p = os.path.join(self.d, "project.json")
        atomic_write_json(p, {"v": 1})
        with mock.patch("desk.fsutil.json.dumps", side_effect=RuntimeError("disk full")):
            with self.assertRaises(RuntimeError):
                atomic_write_json(p, {"v": 2})
        self.assertEqual(read_json(p), {"v": 1})
        self.assertEqual([f for f in os.listdir(self.d) if f.startswith(".tmp-")], [])


class TestMutationTimeoutIsDirty(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="desk_dirty_")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_bridge_mutation_timeout_journaled_dirty(self):
        from desk.bridge import BridgeMutationTimeout
        with self.assertRaises(SystemExit):
            with write_op(self.d, "route_import", "PCB", classification=OP_NON_IDEMPOTENT_MUTATION):
                raise BridgeMutationTimeout("Mutation timeout: operation may have partially succeeded.")
        fails = [r for r in ops.journal(self.d) if r["phase"] == "fail"]
        self.assertEqual(len(fails), 1)
        self.assertTrue(fails[0]["dirty"])
        self.assertEqual(len(ops.pending(self.d)), 1)

    def test_plain_systemexit_still_clean(self):
        with self.assertRaises(SystemExit):
            with write_op(self.d, "build", "B1"):
                raise SystemExit("STOP: validation")
        self.assertFalse(ops.pending(self.d))


class TestReadinessFailClosed(unittest.TestCase):
    def test_unperformed_checks_are_not_reported_verified(self):
        from desk import drc_engine
        cls = next(c for c in vars(drc_engine).values()
                   if isinstance(c, type) and hasattr(c, "evaluate_readiness"))
        rep = cls.evaluate_readiness("proj", [], [])
        self.assertFalse(rep.footprint_integrity_verified)
        self.assertFalse(rep.mechanical_fit_verified)
        self.assertFalse(rep.thermal_clearance_verified)
        self.assertIn("thermal_clearance", rep.checks_not_performed)
        self.assertIn("Checks not performed", rep.summary)


class TestCapabilityRegistry(unittest.TestCase):
    def test_vision_task_gets_vision_model(self):
        from desk.orchestrator.router import _task_for
        from desk.orchestrator.protocol import TaskRequest
        t = TaskRequest(prompt="look", execution_level=1, requires_vision=True,
                        preferred_model="nvidia/nemotron-3.5-lightning-30b-a3b")
        bound = _task_for(t, "pi", 1)
        self.assertEqual(bound.preferred_model, "nvidia/nemotron-3.5-super-vl-120b-a12b")
        self.assertEqual(bound.thinking_level, "off")

    def test_pi_command_has_no_session_and_no_extensions(self):
        from desk.orchestrator.pi_adapter import PiAdapter
        from desk.orchestrator.protocol import TaskRequest
        cmd = PiAdapter(executable_path="pi").build_command(
            TaskRequest(prompt="q", preferred_model="m", thinking_level="off"))
        self.assertIn("--no-session", cmd)
        self.assertIn("-ne", cmd)
        self.assertEqual(cmd[cmd.index("--thinking") + 1], "off")


class TestHttpAdapter(unittest.TestCase):
    def test_body_has_schema_json_mode_and_thinking_off(self):
        from desk.orchestrator.http_adapter import OpenAICompatAdapter
        from desk.orchestrator.protocol import TaskRequest
        a = OpenAICompatAdapter("nvidia", api_key="dummy")
        body = a.build_body(TaskRequest(prompt="q", preferred_model="m", thinking_level="off",
                                        output_schema={"type": "object"}))
        self.assertEqual(body["model"], "m")
        self.assertEqual(body["response_format"], {"type": "json_object"})
        self.assertEqual(body["chat_template_kwargs"], {"enable_thinking": False})
        self.assertIn("JSON schema", body["messages"][0]["content"])
        self.assertEqual(body["messages"][-1], {"role": "user", "content": "q"})

    def test_truncated_reasoning_is_a_failure_not_a_success(self):
        from desk.orchestrator.http_adapter import OpenAICompatAdapter
        from desk.orchestrator.protocol import TaskRequest
        a = OpenAICompatAdapter("nvidia", api_key="dummy")
        fake = {"choices": [{"message": {"content": "", "reasoning_content": "..."}, "finish_reason": "length"}],
                "usage": {"total_tokens": 1565}}

        class R:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return json.dumps(fake).encode()

        with mock.patch("desk.orchestrator.http_adapter.urllib.request.urlopen", return_value=R()):
            res = a.execute(TaskRequest(prompt="q", preferred_model="m", output_schema={"type": "object"},
                                        timeout_sec=5))
        self.assertFalse(res.success)
        self.assertIn("finish_reason=length", res.error)

    def test_missing_key_is_clean_failure(self):
        from desk.orchestrator.http_adapter import OpenAICompatAdapter
        from desk.orchestrator.protocol import TaskRequest
        a = OpenAICompatAdapter("nvidia", api_key_env="DESK_TEST_NO_SUCH_KEY")
        with mock.patch.dict(os.environ, {"DESK_TEST_NO_SUCH_KEY": ""}):
            with mock.patch("desk.auth.broker.get_credential_broker", side_effect=RuntimeError("no vault")):
                res = a.execute(TaskRequest(prompt="q", preferred_model="m", timeout_sec=5))
        self.assertFalse(res.success)
        self.assertIn("No API key", res.error)


class TestProviderOrder(unittest.TestCase):
    def test_env_order_and_preferred_provider(self):
        from desk.orchestrator.router import CapabilityRouter
        from desk.orchestrator.protocol import TaskRequest
        with mock.patch.dict(os.environ, {"DESK_PROVIDER_ORDER": "nvidia,pi,agy"}):
            self.assertEqual(CapabilityRouter._provider_order(TaskRequest(prompt="q")), ["nvidia", "pi", "agy"])
            self.assertEqual(CapabilityRouter._provider_order(TaskRequest(prompt="q", preferred_provider="agy")),
                             ["agy", "nvidia", "pi"])


class TestDoctor(unittest.TestCase):
    def test_doctor_runs_and_reports_every_check(self):
        from desk import doctor
        checks = doctor.run(project=None)
        names = {c.name for c in checks}
        for required in ("Python", "EasyEDA API bridge", "Java runtime", "Freerouting engine", "pi CLI"):
            self.assertIn(required, names)
        self.assertTrue(all(c.status in ("OK", "WARN", "FAIL") for c in checks))
        text = doctor.render(checks)
        self.assertIn("DESK DOCTOR", text)

    def test_doctor_flags_unbound_project(self):
        from desk import doctor
        d = tempfile.mkdtemp(prefix="desk_doc_")
        try:
            with open(os.path.join(d, "project.json"), "w", encoding="utf-8") as h:
                json.dump({"name": "X", "sheet_uuid": "PASTE_FROM tools/ping.py", "pcb_uuid": ""}, h)
            checks = doctor.check_project(d)
            fails = [c for c in checks if c.status == "FAIL"]
            self.assertEqual(len(fails), 2)
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
