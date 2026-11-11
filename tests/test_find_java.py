import os
import shutil
import tempfile
import unittest
from unittest import mock

from desk.routing.orchestrator import find_java, DSNPinMap


class TestFindJava(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="desk_java_")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def _mk(self, rel):
        p = os.path.join(self.d, *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "wb").close()
        return p

    def test_env_override_wins(self):
        exe = self._mk("custom/bin/java.exe")
        with mock.patch.dict(os.environ, {"DESK_JAVA": exe}):
            self.assertEqual(find_java(self.d), exe)

    def test_bundled_jdk_is_found_under_tools(self):
        exe = self._mk("jdk25/jdk-25.0.5+8/bin/java.exe")
        with mock.patch.dict(os.environ, {"DESK_JAVA": ""}):
            self.assertEqual(find_java(self.d), exe)

    def test_falls_back_to_path(self):
        with mock.patch.dict(os.environ, {"DESK_JAVA": ""}):
            with mock.patch("desk.routing.orchestrator.shutil.which", return_value="/usr/bin/java"):
                self.assertEqual(find_java(self.d), "/usr/bin/java")


class TestDSNPinMap(unittest.TestCase):
    def test_maps_pin_ids_to_nets(self):
        dsn = "(network (net GND (pins u1-aacf1a0f31997d0014 u1-fd968fb77a0dceae17)) (net VBUS (pins u1-aacf1a0f31997d0015)))"
        m = DSNPinMap(dsn)
        self.assertEqual(m.nets_in("maze failed for u1-aacf1a0f31997d0015 and u1-fd968fb77a0dceae17"), ["GND", "VBUS"])
        self.assertEqual(m.nets_in("no pins here"), [])


if __name__ == "__main__":
    unittest.main()
