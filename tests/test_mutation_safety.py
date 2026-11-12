"""
Unit tests for Mutation Safety, Atomic Ownership, and Lock Reclamation in desk/ops.py.
"""

import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest import mock

from desk.ops import (
    OP_IDEMPOTENT_MUTATION,
    OP_NON_IDEMPOTENT_MUTATION,
    acquire_atomic_lock,
    pending,
    release_atomic_lock,
    write_op,
)


class TestMutationSafety(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="desk_test_ops_")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_normal_write_op_lifecycle(self):
        with write_op(self.test_dir, "route", "NET_USB", classification=OP_IDEMPOTENT_MUTATION) as rec:
            self.assertEqual(rec["op"], "route")
            lock_path = os.path.join(self.test_dir, "state", "write.lock")
            self.assertTrue(os.path.exists(lock_path))

        # After block exit, lock must be cleanly released
        self.assertFalse(os.path.exists(lock_path))
        # Pending should be empty
        self.assertEqual(len(pending(self.test_dir)), 0)

    def test_lock_release_owner_verification(self):
        state_dir = os.path.join(self.test_dir, "state")
        os.makedirs(state_dir, exist_ok=True)
        lock_path = os.path.join(state_dir, "write.lock")

        # Write lock held by PID 99999 and lock_id "foreign_id"
        with open(lock_path, "w", encoding="utf-8") as f:
            json.dump({"id": "foreign_id", "pid": 99999, "ts": time.time()}, f)

        # Attempt to release with different credentials
        released = release_atomic_lock(lock_path, "my_id", os.getpid())
        self.assertFalse(released)
        # Lock must still exist
        self.assertTrue(os.path.exists(lock_path))

        # Release with correct credentials
        released_correct = release_atomic_lock(lock_path, "foreign_id", 99999)
        self.assertTrue(released_correct)
        self.assertFalse(os.path.exists(lock_path))

    def test_stale_lock_atomic_reclaim(self):
        state_dir = os.path.join(self.test_dir, "state")
        os.makedirs(state_dir, exist_ok=True)
        lock_path = os.path.join(state_dir, "write.lock")

        # Write stale lock with a dead PID (PID 9999999 is dead)
        with open(lock_path, "w", encoding="utf-8") as f:
            json.dump({"id": "stale_id", "pid": 9999999, "ts": time.time() - 3600}, f)

        my_rec = {"id": "new_id", "pid": os.getpid(), "ts": time.time(), "op": "test", "target": "T1"}
        acquire_atomic_lock(lock_path, my_rec, ttl=10)

        # Lock acquired by current process
        with open(lock_path, "r", encoding="utf-8") as f:
            info = json.load(f)
        self.assertEqual(info["id"], "new_id")
        self.assertEqual(info["pid"], os.getpid())

    def test_non_idempotent_mutation_failsafe_dirty(self):
        try:
            with write_op(self.test_dir, "pour_copper", "ZONE_GND", classification=OP_NON_IDEMPOTENT_MUTATION):
                raise RuntimeError("EDA bridge timeout during copper pour")
        except RuntimeError:
            pass

        # Verify target is recorded in pending as dirty
        p = pending(self.test_dir)
        self.assertEqual(len(p), 1)
        self.assertEqual(p[0]["target"], "ZONE_GND")
        self.assertTrue(p[0].get("dirty"))

        # Subsequent write_op on same target MUST be blocked
        with self.assertRaises(SystemExit) as ctx:
            with write_op(self.test_dir, "route", "ZONE_GND"):
                pass
        self.assertIn("unfinished", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()


class TestProcessStartTimeDarwin(unittest.TestCase):
    """F-17: without procfs (macOS/BSD) the start time comes from `ps -o etimes=`, not None."""

    def test_ps_fallback_when_no_procfs(self):
        from desk import ops
        fake = mock.Mock(stdout="120\n")
        with mock.patch.object(ops.os, "name", "posix"), \
             mock.patch.object(ops.os.path, "isdir", return_value=False), \
             mock.patch.object(subprocess, "run", return_value=fake) as run:
            t = ops.get_process_start_time(4242)
        self.assertIsNotNone(t)
        self.assertAlmostEqual(time.time() - t, 120.0, delta=5.0)
        self.assertEqual(run.call_args[0][0][:3], ["ps", "-o", "etimes="])

    def test_ps_failure_returns_none(self):
        from desk import ops
        with mock.patch.object(ops.os, "name", "posix"), \
             mock.patch.object(ops.os.path, "isdir", return_value=False), \
             mock.patch.object(subprocess, "run", side_effect=OSError("no ps")):
            self.assertIsNone(ops.get_process_start_time(4242))

