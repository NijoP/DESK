"""Automated Verification Suite for Routing Engine Orchestrator and Process Supervisor.
Tests binary discovery, Java compatibility checking, headless configuration generation,
and execution supervision.
"""
import unittest
import os
import tempfile
import json
from desk.routing.orchestrator import RoutingEngineOrchestrator


class TestRoutingOrchestrator(unittest.TestCase):

    def setUp(self):
        self.orchestrator = RoutingEngineOrchestrator()

    def test_engine_discovery_finds_compatible_jar(self):
        engine_type, path, ver = self.orchestrator.discover_engine()
        self.assertIn(engine_type, ("JAR", "NATIVE"))
        self.assertTrue(os.path.exists(path))
        # Verify it discovered a compatible version (e.g. v2.1.0 or v2.0.1) and bypassed Java 25 incompatible JARs
        self.assertNotIn("UnsupportedClassVersionError", ver)

    def test_headless_config_generation(self):
        with tempfile.TemporaryDirectory() as td:
            cfg_path = RoutingEngineOrchestrator.ensure_headless_config(td, job_timeout_str="00:03:00")
            self.assertTrue(os.path.exists(cfg_path))
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertFalse(data["gui"]["enabled"])
            self.assertEqual(data["router"]["job_timeout"], "00:03:00")

    def test_missing_input_file_error(self):
        with tempfile.TemporaryDirectory() as td:
            dsn_fake = os.path.join(td, "non_existent.dsn")
            ses_fake = os.path.join(td, "out.ses")
            with self.assertRaises(FileNotFoundError):
                self.orchestrator.execute_routing(dsn_fake, ses_fake)


if __name__ == "__main__":
    unittest.main()
