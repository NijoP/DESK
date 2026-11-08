"""
Unit tests for Component Specifications, Unit Normalization, and V1-V4 Verification.
"""

import time
import unittest

from desk.component_intelligence.identity.models import CanonicalComponent
from desk.component_intelligence.specifications.engine import (
    ComponentSpecification,
    ExtractionMethod,
    SpecificationParser,
)
from desk.component_intelligence.suppliers.models import SupplierOffer
from desk.component_intelligence.verification.engine import (
    ComponentVerificationEngine,
    VerificationLevel,
    VerificationState,
)


class TestSpecificationAndVerification(unittest.TestCase):
    def test_unit_normalization(self):
        # Capacitance
        self.assertAlmostEqual(SpecificationParser.parse_capacitance("10uF"), 1e-5)
        self.assertAlmostEqual(SpecificationParser.parse_capacitance("100nF"), 1e-7)
        self.assertAlmostEqual(SpecificationParser.parse_capacitance("22pF"), 2.2e-11)

        # Resistance
        self.assertAlmostEqual(SpecificationParser.parse_resistance("10k"), 10000.0)
        self.assertAlmostEqual(SpecificationParser.parse_resistance("1M"), 0.001)  # milli-ohm context
        self.assertAlmostEqual(SpecificationParser.parse_resistance("1MEG"), 1000000.0)
        self.assertAlmostEqual(SpecificationParser.parse_resistance("4.7k"), 4700.0)

        # Voltage & Power
        self.assertEqual(SpecificationParser.parse_voltage("16V"), 16.0)
        self.assertEqual(SpecificationParser.parse_power("1/16W"), 0.0625)
        self.assertEqual(SpecificationParser.parse_power("250mW"), 0.25)

    def test_v1_identity_verification(self):
        comp = CanonicalComponent(
            desk_id="comp_1234567812345678",
            manufacturer_name="Texas Instruments",
            normalized_manufacturer="Texas Instruments",
            mpn="TPS62840DLCR",
            normalized_mpn="TPS62840DLCR",
            category="Power Management",
            description="Buck converter",
            package="VSON-8",
        )
        # Check desk_id mismatch detection
        ev_fail = ComponentVerificationEngine.verify_v1_identity(comp)
        self.assertEqual(ev_fail.state, VerificationState.FAIL)
        self.assertTrue(any("mismatch" in v for v in ev_fail.violations))

    def test_v2_electrical_derating_verification(self):
        comp = CanonicalComponent(
            desk_id="comp_c1",
            manufacturer_name="Samsung Electro-Mechanics",
            normalized_manufacturer="Samsung Electro-Mechanics",
            mpn="CL05B104KO5NNNC",
            normalized_mpn="CL05B104KO5NNNC",
            category="Passive Components / Capacitors",
            description="0.1uF 16V MLCC",
            package="0402",
        )
        spec_16v = ComponentSpecification(
            property_name="voltage_rating",
            normalized_value=16.0,
            unit="V",
            original_value="16V",
        )

        # On a 5V rail: 16V >= 1.5 * 5V = 7.5V -> PASS
        ev_pass = ComponentVerificationEngine.verify_v2_electrical(
            comp, [spec_16v], operating_rail_v=5.0
        )
        self.assertEqual(ev_pass.state, VerificationState.PASS)

        # On a 12V rail: 16V < 1.5 * 12V = 18.0V -> FAIL (DC bias derating violation!)
        ev_fail = ComponentVerificationEngine.verify_v2_electrical(
            comp, [spec_16v], operating_rail_v=12.0
        )
        self.assertEqual(ev_fail.state, VerificationState.FAIL)
        self.assertTrue(any("1.5x derating" in v for v in ev_fail.violations))

        # Missing specifications -> UNKNOWN (fail-closed)
        ev_unknown = ComponentVerificationEngine.verify_v2_electrical(comp, [])
        self.assertEqual(ev_unknown.state, VerificationState.UNKNOWN)

    def test_v3_physical_verification(self):
        comp = CanonicalComponent(
            desk_id="comp_ic1",
            manufacturer_name="STMicroelectronics",
            normalized_manufacturer="STMicroelectronics",
            mpn="STM32F401CCU6",
            normalized_mpn="STM32F401CCU6",
            category="Microcontrollers",
            description="MCU",
            package="UFQFPN-48",
        )
        footprint_48 = [{"num": str(i), "name": f"P{i}"} for i in range(1, 49)]
        ev_pass = ComponentVerificationEngine.verify_v3_physical(
            comp, footprint_pins=footprint_48, expected_pin_count=48
        )
        self.assertEqual(ev_pass.state, VerificationState.PASS)

        # Mismatch in pin count
        footprint_32 = [{"num": str(i), "name": f"P{i}"} for i in range(1, 33)]
        ev_fail = ComponentVerificationEngine.verify_v3_physical(
            comp, footprint_pins=footprint_32, expected_pin_count=48
        )
        self.assertEqual(ev_fail.state, VerificationState.FAIL)

    def test_v4_procurement_verification(self):
        # Fresh offer with sufficient inventory -> PASS
        offer = SupplierOffer(
            supplier_id="lcsc",
            supplier_name="LCSC Electronics",
            sku="C11702",
            canonical_desk_id="c1",
            manufacturer_name="Uni-Royal",
            mpn="0402WGF1001TCE",
            stock=5000,
            unit_price=0.003,
            last_checked_ts=time.time(),
        )
        ev_pass = ComponentVerificationEngine.verify_v4_procurement(offer, required_quantity=100)
        self.assertEqual(ev_pass.state, VerificationState.PASS)

        # Insufficient inventory -> FAIL
        ev_shortage = ComponentVerificationEngine.verify_v4_procurement(offer, required_quantity=10000)
        self.assertEqual(ev_shortage.state, VerificationState.FAIL)

        # Quote older than 7 days -> STALE
        stale_offer = SupplierOffer(
            supplier_id="lcsc",
            supplier_name="LCSC Electronics",
            sku="C11702",
            canonical_desk_id="c1",
            manufacturer_name="Uni-Royal",
            mpn="0402WGF1001TCE",
            stock=5000,
            unit_price=0.003,
            last_checked_ts=time.time() - (10 * 86400),  # 10 days old
        )
        ev_stale = ComponentVerificationEngine.verify_v4_procurement(stale_offer, required_quantity=100)
        self.assertEqual(ev_stale.state, VerificationState.STALE)


if __name__ == "__main__":
    unittest.main()
