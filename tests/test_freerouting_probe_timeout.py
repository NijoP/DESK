"""Regression (UPS_1000 F-007): a JAR whose --help blocks after printing its banner is compatible; a timeout
without a banner, or with UnsupportedClassVersionError, is not. Ported from branch ups-1000-live-test."""
import subprocess, unittest
from unittest import mock
import desk.routing.orchestrator as o

CLS = o.RoutingEngineOrchestrator


class ProbeTimeout(unittest.TestCase):
    def _probe(self, out):
        inst = CLS.__new__(CLS)
        inst.java = "java"
        exc = subprocess.TimeoutExpired(cmd=["java"], timeout=25, output=out, stderr=b"")
        with mock.patch.object(o.subprocess, "run", side_effect=exc):
            return inst._probe_jar_compatibility("x.jar")

    def test_banner_then_hang_is_compatible(self):
        self.assertEqual(self._probe(b"INFO   Freerouting v2.1.0 (build-date: 2025-04-12)\n"), (True, "v2.1.0"))

    def test_timeout_without_banner_is_not(self):
        self.assertFalse(self._probe(b"")[0])

    def test_class_version_error_is_not(self):
        self.assertFalse(self._probe(b"Freerouting v2.5.0\nUnsupportedClassVersionError")[0])


if __name__ == "__main__":
    unittest.main()
