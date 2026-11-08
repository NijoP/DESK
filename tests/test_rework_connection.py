"""
Unit tests for DESK Rework Mode ECAD Connection and Project Binding.
Zero external dependencies.
"""

import json
import os
import shutil
import tempfile
import unittest

from desk.rework import (
    ProjectBinding,
    ECADConnectionManager,
    ConnectionDiscoveryError,
    ProjectMismatchError,
)


class TestReworkConnection(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.meta_file = os.path.join(self.tmp_dir, "project.json")
        with open(self.meta_file, "w", encoding="utf-8") as f:
            json.dump({
                "name": "TEST_CONTROLLER",
                "uuid": "uuid_proj_12345",
                "pcb_uuid": "pcb_doc_9999",
                "sheet_uuid": "sch_doc_8888",
            }, f)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_project_binding_from_local_metadata(self):
        """Validates that project binding correctly ingests metadata."""
        binding = ProjectBinding(
            project_name="TEST_CONTROLLER",
            project_path=self.tmp_dir,
            project_uuid="uuid_proj_12345",
            window_id="win_101",
            eda_port=49620,
            pcb_uuid="pcb_doc_9999",
            sheet_uuid="sch_doc_8888",
            is_confirmed=True,
        )
        self.assertEqual(binding.project_name, "TEST_CONTROLLER")
        self.assertEqual(binding.window_id, "win_101")
        self.assertTrue(binding.is_confirmed)

        d = binding.to_dict()
        restored = ProjectBinding.from_dict(d)
        self.assertEqual(restored.project_uuid, "uuid_proj_12345")

    def test_offline_binding_verification(self):
        """Validates safe offline verification when no live EasyEDA window is running."""
        binding = ProjectBinding(
            project_name="TEST_CONTROLLER",
            project_path=self.tmp_dir,
            project_uuid="uuid_proj_12345",
            window_id="offline",
            eda_port=49620,
        )
        self.assertTrue(ECADConnectionManager.verify_binding(binding))


if __name__ == "__main__":
    unittest.main()
