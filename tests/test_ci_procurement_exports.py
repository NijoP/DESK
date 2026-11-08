"""Tests for Specialized BOM and CPL Exports, and Multi-Supplier Sourcing."""

import os
import unittest
import tempfile
import shutil
import csv
from desk.component_intelligence.procurement.engine import ProcurementLineItem, ProcurementBOMReport
from desk.component_intelligence.procurement.bom_export import (
    export_jlcpcb_bom,
    export_jlcpcb_cpl,
    export_lcsc_bom,
)
from desk.component_intelligence.suppliers.providers.mouser.provider import MouserSupplierProvider


class TestProcurementExportsAndMouser(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.sample_report = ProcurementBOMReport(
            batch_quantity=10,
            total_extended_cost=45.50,
            line_items=[
                ProcurementLineItem(
                    designators=["C1", "C2"],
                    required_quantity=20,
                    mpn="GRM155R71C104KA88D",
                    manufacturer="Murata",
                    package="0402",
                    selected_supplier="LCSC",
                    selected_sku="C15849",
                    available_stock=50000,
                    unit_price=0.005,
                    extended_price=0.10,
                ),
                ProcurementLineItem(
                    designators=["U1"],
                    required_quantity=10,
                    mpn="STM32F405RGT6",
                    manufacturer="STMicroelectronics",
                    package="LQFP-64",
                    selected_supplier="Mouser",
                    selected_sku="511-STM32F405RGT6",
                    available_stock=4200,
                    unit_price=13.20,
                    extended_price=132.0,
                ),
            ],
        )

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_export_jlcpcb_bom(self):
        bom_file = os.path.join(self.tmp_dir, "jlcpcb_bom.csv")
        export_jlcpcb_bom(self.sample_report, bom_file)
        self.assertTrue(os.path.exists(bom_file))

        with open(bom_file, "r", encoding="utf-8") as f:
            reader = list(csv.reader(f))
            self.assertEqual(reader[0], ["Comment", "Designator", "Footprint", "LCSC Part #"])
            self.assertEqual(reader[1], ["GRM155R71C104KA88D", "C1,C2", "0402", "C15849"])
            # Mouser line has empty LCSC part #
            self.assertEqual(reader[2], ["STM32F405RGT6", "U1", "LQFP-64", ""])

    def test_export_jlcpcb_cpl_with_rotation(self):
        cpl_file = os.path.join(self.tmp_dir, "jlcpcb_cpl.csv")
        placements = [
            {"id": "U1", "val": "AMS1117", "package": "SOT-223", "x": 12.5, "y": 25.0, "rotation": 0.0, "layer": "Top"},
            {"id": "D1", "val": "1N4148", "package": "SOD-123", "x": 15.0, "y": 30.0, "rotation": 90.0, "layer": 1},
            {"id": "C1", "val": "100nF", "package": "0402", "x": 5.0, "y": 10.0, "rotation": 0.0, "layer": "Bottom"},
        ]
        export_jlcpcb_cpl(placements, cpl_file)
        self.assertTrue(os.path.exists(cpl_file))

        with open(cpl_file, "r", encoding="utf-8") as f:
            reader = list(csv.reader(f))
            self.assertEqual(reader[0], ["Designator", "Val", "Package", "Mid X", "Mid Y", "Rotation", "Layer"])
            
            # SOT-223 offset is +180 deg: 0.0 -> 180.0
            self.assertEqual(reader[1][0], "U1")
            self.assertEqual(float(reader[1][5]), 180.0)
            self.assertEqual(reader[1][6], "Top")

            # SOD-123 offset is +180 deg: 90.0 + 180.0 = 270.0
            self.assertEqual(reader[2][0], "D1")
            self.assertEqual(float(reader[2][5]), 270.0)
            self.assertEqual(reader[2][6], "Top")

            # 0402 offset is 0.0 deg: 0.0 -> 0.0
            self.assertEqual(reader[3][0], "C1")
            self.assertEqual(float(reader[3][5]), 0.0)
            self.assertEqual(reader[3][6], "Bottom")

    def test_export_lcsc_bom(self):
        lcsc_file = os.path.join(self.tmp_dir, "lcsc_bom.csv")
        export_lcsc_bom(self.sample_report, lcsc_file)
        self.assertTrue(os.path.exists(lcsc_file))

        with open(lcsc_file, "r", encoding="utf-8") as f:
            reader = list(csv.reader(f))
            self.assertEqual(reader[0], ["Item", "Quantity", "LCSC Part Number", "Manufacturer Part", "Customer Reference"])
            self.assertEqual(reader[1], ["1", "20", "C15849", "GRM155R71C104KA88D", "C1 C2"])

    def test_mouser_provider(self):
        mouser = MouserSupplierProvider(use_mock=True)
        offers = mouser.get_offers("TPS62840DLYR")
        self.assertEqual(len(offers), 1)
        self.assertEqual(offers[0].sku, "595-TPS62840DLYR")
        self.assertEqual(offers[0].stock, 18500)
        self.assertEqual(offers[0].get_price_for_quantity(50), 1.45)


if __name__ == "__main__":
    unittest.main()
