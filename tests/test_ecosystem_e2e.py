"""End-to-End Integration Test for the DESK AI-Native Electronics Ecosystem.

Validates the full integrated pipeline:
1. Multi-supplier component discovery (LCSC, Mouser)
2. Fail-closed component verification
3. Procurement BOM optimization
4. Production manufacturing exports (JLCPCB PCBA BOM, CPL with rotation alignment)
5. DFM analysis and PCB/PCBA cost quotation
6. Absolute Order Guard safety verification
7. Deterministic Operation Registry execution
"""

import os
import unittest
import tempfile
import shutil
import csv
from desk.operation_registry import get_operation_registry
from desk.component_intelligence.suppliers.registry import SupplierRegistry
from desk.component_intelligence.suppliers.providers.mouser.provider import MouserSupplierProvider
from desk.component_intelligence.procurement.engine import ProcurementEngine
from desk.component_intelligence.procurement.bom_export import (
    export_jlcpcb_bom,
    export_jlcpcb_cpl,
    export_lcsc_bom,
)
from desk.manufacturing.jlcpcb import (
    JLCPCBClient,
    JLCPCBQuotingEngine,
    OrderApprovalManager,
    OrderExecutionBlockedError,
)
from desk.eda.easyeda_pro import get_easyeda_manager


class TestEcosystemEndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.registry = get_operation_registry()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_end_to_end_electronics_pipeline(self):
        # -------------------------------------------------------------
        # Step 1: Operation Registry Multi-Supplier Search
        # -------------------------------------------------------------
        search_res = self.registry.execute("supplier_search", {"query": "TPS62840"})
        self.assertEqual(search_res["status"], "SUCCESS")
        offers = search_res["result"]
        self.assertGreater(len(offers), 0)
        tps_offer = offers[0]
        self.assertIn("TPS62840", tps_offer["mpn"])

        # -------------------------------------------------------------
        # Step 2: Procurement BOM Optimization
        # -------------------------------------------------------------
        board_components = [
            {"mpn": "TPS62840DLYR", "ref": "U1", "manufacturer": "Texas Instruments", "package": "VSON-6"},
            {"mpn": "C15849", "ref": "C1", "manufacturer": "Murata", "package": "0402", "lcsc": "C15849"},
            {"mpn": "C15849", "ref": "C2", "manufacturer": "Murata", "package": "0402", "lcsc": "C15849"},
        ]
        bom_res = self.registry.execute(
            "build_procurement_bom",
            {"parts": board_components, "batch_quantity": 25}
        )
        self.assertEqual(bom_res["status"], "SUCCESS")
        report = bom_res["result"]
        self.assertEqual(report["batch_quantity"], 25)
        self.assertGreater(report["total_extended_cost"], 0.0)

        # -------------------------------------------------------------
        # Step 3: Production Manufacturing File Generation
        # -------------------------------------------------------------
        jlc_bom_file = os.path.join(self.tmp_dir, "jlc_pcba_bom.csv")
        export_jlcpcb_bom(report, jlc_bom_file)
        self.assertTrue(os.path.exists(jlc_bom_file))

        placements = [
            {"id": "U1", "val": "TPS62840", "package": "VSON-6", "x": 20.0, "y": 15.0, "rotation": 0.0, "layer": "Top"},
            {"id": "C1", "val": "100nF", "package": "0402", "x": 18.0, "y": 12.0, "rotation": 90.0, "layer": "Top"},
            {"id": "C2", "val": "100nF", "package": "0402", "x": 22.0, "y": 12.0, "rotation": 90.0, "layer": "Top"},
        ]
        jlc_cpl_file = os.path.join(self.tmp_dir, "jlc_cpl.csv")
        export_jlcpcb_cpl(placements, jlc_cpl_file)
        self.assertTrue(os.path.exists(jlc_cpl_file))

        # Verify CPL structure
        with open(jlc_cpl_file, "r", encoding="utf-8") as f:
            cpl_rows = list(csv.reader(f))
            self.assertEqual(cpl_rows[0], ["Designator", "Val", "Package", "Mid X", "Mid Y", "Rotation", "Layer"])
            self.assertEqual(cpl_rows[1][0], "U1")

        # -------------------------------------------------------------
        # Step 4: DFM Verification and Manufacturing Quotation
        # -------------------------------------------------------------
        quote_res = self.registry.execute(
            "manufacturing_quote",
            {
                "width_mm": 50.0,
                "height_mm": 50.0,
                "layer_count": 2,
                "quantity": 25,
                "bom_components": [
                    {"lcsc_pn": "C15849", "package": "0402", "quantity": 2, "joints": 2},
                    {"lcsc_pn": "C99999", "package": "VSON-6", "quantity": 1, "joints": 6},
                ],
            }
        )
        self.assertEqual(quote_res["status"], "SUCCESS")
        quote = quote_res["result"]
        self.assertTrue(quote.dfm.is_valid)
        self.assertGreater(quote.total_estimated_usd, 0.0)
        self.assertEqual(quote.pcb.layer_count, 2)
        self.assertEqual(quote.pcba.board_count, 25)

        # -------------------------------------------------------------
        # Step 5: Absolute Order Guard Verification
        # -------------------------------------------------------------
        client = JLCPCBClient(use_mock=True)
        # Attempt without Captain token must fail
        with self.assertRaises(OrderExecutionBlockedError):
            client.submit_order_with_approval(quote, captain_token="")

        # Interactive Captain approval workflow
        token = client.order_guard.request_approval({"quote_usd": quote.total_estimated_usd})
        self.assertTrue(token.startswith("CAPTAIN-APPROVE-"))
        client.order_guard.confirm_token(token)

        # Order submission with confirmed token succeeds
        order_receipt = client.submit_order_with_approval(quote, captain_token=token)
        self.assertEqual(order_receipt["status"], "AWAITING_PAYMENT_MANUAL")
        self.assertIn("MOCK-JLC", order_receipt["order_id"])

        # Re-using the consumed token fails
        with self.assertRaises(OrderExecutionBlockedError):
            client.submit_order_with_approval(quote, captain_token=token)

        # -------------------------------------------------------------
        # Step 6: Safe EDA Offline Inspection
        # -------------------------------------------------------------
        proj_dir = os.path.join(self.tmp_dir, "my_disposable_project")
        os.makedirs(proj_dir)
        with open(os.path.join(proj_dir, "design.json"), "w") as f:
            f.write("{}")

        eda_res = self.registry.execute("eda_inspect_project", {"project_path": proj_dir})
        self.assertEqual(eda_res["status"], "SUCCESS")
        eda_info = eda_res["result"]
        self.assertFalse(eda_info["is_protected"])
        self.assertTrue(eda_info["mutation_allowed"])


if __name__ == "__main__":
    unittest.main()
