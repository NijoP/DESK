"""Contract and offline mock tests for EasyEDA Pro PCB Adapter.
Validates script generation, payload parsing, and status assertions without live bridge calls.
"""
import unittest
from desk.adapters.easyeda_pcb_adapter import EasyEDAPcbAdapter, PCBReadbackData

class TestEasyEDAPcbAdapter(unittest.TestCase):

    def setUp(self):
        self.adapter = EasyEDAPcbAdapter()
        self.fake_pcb_uuid = "pcb_uuid_abc123"

    def test_01_build_batch_readback_script(self):
        script = self.adapter.build_batch_readback_script(self.fake_pcb_uuid)
        self.assertIn("eda.pcb_PrimitiveComponent.getAllPrimitiveId()", script)
        self.assertIn("eda.pcb_PrimitiveLine.getAll()", script)
        self.assertIn("eda.pcb_PrimitiveVia.getAll()", script)
        self.assertIn("eda.pcb_PrimitivePour.getAll()", script)
        self.assertIn("eda.pcb_PrimitivePoured.getAll()", script)
        self.assertIn("eda.pcb_Layer.getCurrentPhysicalStackingConfiguration()", script)
        self.assertIn("eda.pcb_Drc.getAllNetClasses()", script)
        self.assertIn(self.fake_pcb_uuid, script)

    def test_02_parse_readback_payload(self):
        mock_payload = {
            "ok": True,
            "components": {
                "R1": {"id": "c1", "x": 1000, "y": 2000, "rot": 0, "layer": 1, "pads": [
                    {"num": "1", "x": 980, "y": 2000, "net": "3V3", "layer": 1},
                    {"num": "2", "x": 1020, "y": 2000, "net": "SW", "layer": 1}
                ]}
            },
            "tracks": [
                {"id": "l1", "x1": 100, "y1": 100, "x2": 200, "y2": 100, "width": 10, "layer": 1, "net": "SW"}
            ],
            "vias": [
                {"id": "v1", "x": 200, "y": 100, "hole_dia": 12, "dia": 24, "net": "GND"}
            ],
            "zones": [
                {"id": "p1", "name": "GND_ZONE", "net": "GND", "layer": 2, "priority": 1}
            ],
            "poured_regions": [
                {"id": "pr1", "net": "GND", "layer": 2}
            ],
            "stackup": {"layerCount": 4, "name": "Standard 4-Layer"},
            "net_classes": [{"name": "POWER", "nets": ["VIN", "SW", "VBAT"]}],
            "diff_pairs": [{"name": "USB", "positiveNet": "USB_DP", "negativeNet": "USB_DN"}]
        }

        data = self.adapter.parse_readback_payload("TEST_PROJ", self.fake_pcb_uuid, mock_payload)
        self.assertEqual(data.project_name, "TEST_PROJ")
        self.assertEqual(data.pcb_uuid, self.fake_pcb_uuid)
        self.assertIn("R1", data.components)
        self.assertEqual(len(data.tracks), 1)
        self.assertEqual(len(data.vias), 1)
        self.assertEqual(len(data.zones), 1)
        self.assertEqual(len(data.poured_regions), 1)
        self.assertEqual(data.net_classes[0]["name"], "POWER")
        self.assertEqual(data.raw_status, "PARSED_OK")

    def test_03_build_create_zone_script(self):
        pts = [(100.0, 100.0), (500.0, 100.0), (500.0, 400.0), (100.0, 400.0)]
        script = self.adapter.build_create_zone_script(
            pcb_uuid=self.fake_pcb_uuid,
            net="GND",
            layer=2,
            points_mil=pts,
            name="BOTTOM_GND",
            priority=1,
            spoke_width_mil=12.0
        )
        self.assertIn("eda.pcb_MathPolygon.createPolygon", script)
        self.assertIn("eda.pcb_PrimitivePour.create", script)
        self.assertIn('"GND"', script)
        self.assertIn('"BOTTOM_GND"', script)
        self.assertIn(self.fake_pcb_uuid, script)

    def test_04_build_modify_zone_script(self):
        script = self.adapter.build_modify_zone_script(
            self.fake_pcb_uuid, "pour_123", {"net": "3V3", "pourPriority": 3}
        )
        self.assertIn('eda.pcb_PrimitivePour.modify("pour_123"', script)
        self.assertIn('"3V3"', script)
        self.assertIn(self.fake_pcb_uuid, script)

    def test_05_build_repour_all_script(self):
        script = self.adapter.build_repour_all_script(self.fake_pcb_uuid)
        self.assertIn("eda.pcb_PrimitivePour.getAll()", script)
        self.assertIn("rebuildCopperRegion()", script)
        self.assertIn(self.fake_pcb_uuid, script)

    def test_06_unverified_status_markers(self):
        # Assert honest status marking on mutation methods
        self.assertEqual(EasyEDAPcbAdapter.STATUS_READBACK, "IMPLEMENTED_AND_TESTED_OFFLINE")
        self.assertEqual(EasyEDAPcbAdapter.STATUS_COPPER_MUTATION, "NOT_LIVE_VERIFIED")
        self.assertEqual(EasyEDAPcbAdapter.STATUS_REPOUR, "NOT_LIVE_VERIFIED")

if __name__ == "__main__":
    unittest.main()
