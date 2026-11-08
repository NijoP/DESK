"""Tests for JLCPCB Manufacturing, Quotation, DFM and Order Guard Safety."""

import unittest
from desk.manufacturing.jlcpcb import (
    JLCPCBClient,
    JLCPCBPCBACatalog,
    PartAssemblyType,
    JLCPCBQuotingEngine,
    OrderApprovalManager,
    OrderExecutionBlockedError,
)


class TestJLCPCBManufacturing(unittest.TestCase):
    def setUp(self):
        self.engine = JLCPCBQuotingEngine()
        self.client = JLCPCBClient(use_mock=True)

    def test_pcba_part_classification(self):
        # Known basic part
        basic = JLCPCBPCBACatalog.classify_part("C15849", "0402")
        self.assertEqual(basic.part_type, PartAssemblyType.BASIC)
        self.assertEqual(basic.feeder_fee_usd, 0.0)

        # Extended part
        ext = JLCPCBPCBACatalog.classify_part("C999999", "QFN-32")
        self.assertEqual(ext.part_type, PartAssemblyType.EXTENDED)
        self.assertEqual(ext.feeder_fee_usd, 3.00)

    def test_rotation_offsets(self):
        self.assertEqual(JLCPCBPCBACatalog.get_rotation_offset("SOT-223"), 180.0)
        self.assertEqual(JLCPCBPCBACatalog.get_rotation_offset("SOT-23-5"), 0.0)
        self.assertEqual(JLCPCBPCBACatalog.get_rotation_offset("SOD-123"), 180.0)

        norm_rot = JLCPCBPCBACatalog.normalize_rotation(270.0, "SOT-223")
        self.assertEqual(norm_rot, 90.0)

    def test_dfm_validation(self):
        # Valid parameters
        dfm_ok = self.engine.validate_dfm(
            width_mm=50.0,
            height_mm=50.0,
            layer_count=2,
            min_trace_mil=5.0,
            min_spacing_mil=5.0,
            min_drill_mm=0.3,
        )
        self.assertTrue(dfm_ok.is_valid)
        self.assertEqual(len(dfm_ok.violations), 0)

        # Violation: min trace < 3.5 mil
        dfm_bad = self.engine.validate_dfm(
            width_mm=50.0,
            height_mm=50.0,
            layer_count=2,
            min_trace_mil=2.5,
            min_spacing_mil=5.0,
            min_drill_mm=0.3,
        )
        self.assertFalse(dfm_bad.is_valid)
        self.assertTrue(any("Minimum trace width" in v for v in dfm_bad.violations))

    def test_pcb_quotation(self):
        quote_item = self.engine.calculate_pcb_quote(
            width_mm=80.0,
            height_mm=60.0,
            layer_count=2,
            quantity=5,
            surface_finish="HASL",
        )
        self.assertEqual(quote_item.estimated_usd, 2.00)

        # 4-layer board
        quote_4l = self.engine.calculate_pcb_quote(
            width_mm=80.0,
            height_mm=60.0,
            layer_count=4,
            quantity=5,
            surface_finish="HASL",
        )
        self.assertEqual(quote_4l.estimated_usd, 12.00)

    def test_pcba_quotation(self):
        bom = [
            {"lcsc_pn": "C15849", "package": "0402", "quantity": 10, "joints": 2},  # Basic: $0 feeder
            {"lcsc_pn": "C999999", "package": "QFN-32", "quantity": 1, "joints": 32},  # Extended: $3 feeder
        ]
        pcba_item = self.engine.calculate_pcba_quote(board_count=5, bom_components=bom)
        self.assertEqual(pcba_item.unique_parts_count, 2)
        self.assertEqual(pcba_item.basic_parts_count, 1)
        self.assertEqual(pcba_item.extended_parts_count, 1)
        self.assertEqual(pcba_item.feeder_fees_usd, 3.00)
        self.assertEqual(pcba_item.setup_fee_usd, 8.00)
        # Total should include setup + feeder + joints
        self.assertGreater(pcba_item.estimated_usd, 11.00)

    def test_order_guard_blocks_unauthorized_order(self):
        quote = self.client.get_quote(width_mm=50, height_mm=50, layer_count=2)
        
        # Test 1: No token
        with self.assertRaises(OrderExecutionBlockedError):
            self.client.submit_order_with_approval(quote, captain_token="")

        # Test 2: Unconfirmed token
        guard = OrderApprovalManager()
        token = guard.request_approval({"total_usd": quote.total_estimated_usd})
        with self.assertRaises(OrderExecutionBlockedError):
            guard.verify_and_consume(token)

        # Test 3: Confirmed token succeeds and consumes
        guard.confirm_token(token)
        self.assertTrue(guard.verify_and_consume(token))

        # Test 4: Reuse of consumed token fails
        with self.assertRaises(OrderExecutionBlockedError):
            guard.verify_and_consume(token)


if __name__ == "__main__":
    unittest.main()
