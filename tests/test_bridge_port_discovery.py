"""
Unit tests for DESK ECAD Bridge Port Discovery and SessionRegistry Caching.
Validates cold discovery, warm caching, environment override, concurrent probing,
stale recovery, and endpoint invalidation.
Zero external dependencies.
"""

import os
import socket
import time
import unittest
from desk.bridge import SessionRegistry


class TestBridgePortDiscovery(unittest.TestCase):

    def setUp(self):
        SessionRegistry.invalidate_port_cache()
        if "EDA_PORT" in os.environ:
            del os.environ["EDA_PORT"]

    def tearDown(self):
        SessionRegistry.invalidate_port_cache()
        if "EDA_PORT" in os.environ:
            del os.environ["EDA_PORT"]

    def test_env_var_override(self):
        """Validates that explicit EDA_PORT environment variable takes absolute precedence."""
        os.environ["EDA_PORT"] = "49628"
        t0 = time.perf_counter()
        port = SessionRegistry.get_port()
        duration_ms = (time.perf_counter() - t0) * 1000.0
        self.assertEqual(port, 49628)
        self.assertLess(duration_ms, 5.0)

    def test_warm_discovery_in_memory_cache(self):
        """Validates that warm discovery takes < 1 ms by reusing in-memory cache."""
        # First call (cold or probe)
        SessionRegistry.get_port(timeout=0.02)
        # Second call (warm)
        t0 = time.perf_counter()
        p_warm = SessionRegistry.get_port()
        warm_ms = (time.perf_counter() - t0) * 1000.0

        self.assertEqual(p_warm, 49620)
        self.assertLess(warm_ms, 1.0)

    def test_cold_discovery_bounded_time(self):
        """Validates that even when all ports are closed, cold probe completes well within bound (< 150ms)."""
        SessionRegistry.invalidate_port_cache()
        t0 = time.perf_counter()
        port = SessionRegistry.get_port(timeout=0.02, force_probe=True)
        cold_ms = (time.perf_counter() - t0) * 1000.0

        self.assertEqual(port, 49620)
        self.assertLess(cold_ms, 150.0)

    def test_discovery_finds_active_default_port(self):
        """Validates immediate discovery when default port 49620 is active."""
        already_active = SessionRegistry._probe_single_port(49620)
        srv = None
        if not already_active:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                srv.bind(("127.0.0.1", 49620))
                srv.listen(1)
            except OSError:
                srv.close()
                srv = None

        try:
            SessionRegistry.invalidate_port_cache()
            t0 = time.perf_counter()
            port = SessionRegistry.get_port(timeout=0.02, force_probe=True)
            active_ms = (time.perf_counter() - t0) * 1000.0

            self.assertEqual(port, 49620)
            self.assertLess(active_ms, 30.0)
        finally:
            if srv:
                srv.close()

    def test_discovery_finds_active_candidate_port(self):
        """Validates concurrent probe discovery when a non-default candidate port (e.g. 49623) is active."""
        if SessionRegistry._probe_single_port(49620):
            self.skipTest("Default port 49620 is actively in use by running ECAD process")

        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.bind(("127.0.0.1", 49623))
        srv.listen(1)

        try:
            SessionRegistry.invalidate_port_cache()
            t0 = time.perf_counter()
            # 0.3 s per probe: a loaded CI runner (macOS, 55 s suite) missed 49623 within 30 ms and fell back to 49620.
            port = SessionRegistry.get_port(timeout=0.3, force_probe=True)
            active_ms = (time.perf_counter() - t0) * 1000.0

            self.assertEqual(port, 49623)
            self.assertLess(active_ms, 2000.0)   # correctness test; the sub-80 ms figure is a dev-machine benchmark, not a CI gate
        finally:
            srv.close()

    def test_invalidate_port_cache_clears_state(self):
        """Validates that invalidation forces a re-probe."""
        SessionRegistry.get_port()
        self.assertIsNotNone(SessionRegistry._discovered_port)

        SessionRegistry.invalidate_port_cache()
        self.assertIsNone(SessionRegistry._discovered_port)
        self.assertEqual(SessionRegistry._last_port_check, 0.0)

    def test_stale_endpoint_recovery(self):
        """Validates that a stale persistent cache pointing to an inactive port safely recovers."""
        # Write stale cache pointing to 49629
        SessionRegistry._write_persistent_cache(49629)
        SessionRegistry._discovered_port = None
        SessionRegistry._last_port_check = 0.0

        # Port 49629 is not open, so get_port must safely fall back to 49620
        port = SessionRegistry.get_port(timeout=0.02)
        self.assertEqual(port, 49620)


if __name__ == "__main__":
    unittest.main()
