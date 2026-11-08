"""
Unit tests for ProcessGuard and Bounded Subprocess Execution.
"""

import os
import sys
import tempfile
import threading
import time
import unittest

from desk.runtime.process_guard import ProcessGuard


class TestProcessGuard(unittest.TestCase):
    def test_normal_execution(self):
        cmd = [sys.executable, "-c", "print('hello process guard')"]
        res = ProcessGuard.run_bounded(cmd, timeout_s=5.0)
        self.assertEqual(res.exit_code, 0)
        self.assertIn("hello process guard", res.stdout)
        self.assertFalse(res.timed_out)
        self.assertFalse(res.truncated)

    def test_non_zero_exit(self):
        cmd = [sys.executable, "-c", "import sys; sys.stderr.write('fatal error\\n'); sys.exit(42)"]
        res = ProcessGuard.run_bounded(cmd, timeout_s=5.0)
        self.assertEqual(res.exit_code, 42)
        self.assertIn("fatal error", res.stderr)
        self.assertFalse(res.timed_out)

    def test_bounded_output_truncation(self):
        # Generate 200 KB of text
        cmd = [sys.executable, "-c", "import sys; sys.stdout.write('A' * 200000)"]
        max_bytes = 4096  # Cap in memory at 4 KB
        res = ProcessGuard.run_bounded(cmd, timeout_s=5.0, max_buffer_bytes=max_bytes)
        self.assertEqual(res.exit_code, 0)
        self.assertEqual(len(res.stdout), max_bytes)
        self.assertTrue(res.truncated)

    def test_durable_disk_log_preservation(self):
        # In-memory buffer is capped at 1 KB, but disk log must capture all 100 KB
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            log_path = tmp.name

        try:
            cmd = [sys.executable, "-c", "import sys; sys.stdout.write('X' * 100000)"]
            res = ProcessGuard.run_bounded(
                cmd,
                timeout_s=5.0,
                max_buffer_bytes=1024,
                log_file_path=log_path,
            )
            self.assertEqual(res.exit_code, 0)
            self.assertEqual(len(res.stdout), 1024)
            self.assertTrue(res.truncated)

            # Verify disk log has full output
            with open(log_path, "rb") as f:
                disk_content = f.read()
            self.assertEqual(len(disk_content), 100000)
            self.assertEqual(disk_content, b"X" * 100000)
        finally:
            if os.path.exists(log_path):
                os.remove(log_path)

    def test_timeout_and_tree_kill(self):
        # Process that attempts to sleep for 10 seconds, timeout at 0.3s
        cmd = [sys.executable, "-c", "import time; time.sleep(10.0)"]
        t0 = time.time()
        res = ProcessGuard.run_bounded(cmd, timeout_s=0.3)
        duration = time.time() - t0
        self.assertTrue(res.timed_out)
        self.assertEqual(res.exit_code, -1)
        self.assertLess(duration, 3.0)  # Must terminate promptly

    def test_cancellation(self):
        cancel_evt = threading.Event()

        def _cancel_soon():
            time.sleep(0.15)
            cancel_evt.set()

        threading.Thread(target=_cancel_soon, daemon=True).start()
        cmd = [sys.executable, "-c", "import time; time.sleep(10.0)"]
        res = ProcessGuard.run_bounded(cmd, timeout_s=5.0, cancellation_event=cancel_evt)
        self.assertTrue(res.cancelled)
        self.assertEqual(res.exit_code, -1)


if __name__ == "__main__":
    unittest.main()
