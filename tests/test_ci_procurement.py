"""
Unit tests for Component Alternatives Engine and Multi-Supplier BOM Procurement Engine.
"""

import os
import tempfile
import unittest

from desk.component_intelligence.catalog.alternatives import (
    CompatibilityLevel,
    ComponentAlternativesEngine,
)
from desk.component_intelligence.identity.models import CanonicalComponent
from desk.component_intelligence.procurement.engine import ProcurementEngine
from desk.component_intelligence.specifications.engine import ComponentSpecification
from desk.component_intelligence.suppliers.models import PriceBreak, SupplierOffer
from desk.component_intelligence.suppliers.providers.lcsc.provider import LcscSupplierProvider
from desk.component_intelligence.suppliers.registry import SupplierRegistry


class TestProcurementAndAlternatives(unittest.TestCase):
    def test_alternatives_evaluation(self):
        primary = CanonicalComponent(
            desk_id="comp_bjt_1",
            manufacturer_name="onsemi",
            normalized_manufacturer="onsemi",
            mpn="BSS138",
            normalized_mpn="BSS138",
            category="Transistors",
            description="50V N-Ch MOSFET",
            package="SOT-23",
        )
        p_specs = [
            ComponentSpecification("voltage", 50.0, "V", "50V"),
            ComponentSpecification("current", 0.22, "A", "220mA"),
        ]

        # Candidate with higher voltage (60V) and matching package -> PIN_COMPATIBLE
        candidate = CanonicalComponent(
            desk_id="comp_bjt_2",
            manufacturer_name="Diodes Incorporated",
            normalized_manufacturer="Diodes Incorporated",
            mpn="2N7002",
            normalized_mpn="2N7002",
            category="Transistors",
            description="60V N-Ch MOSFET",
            package="SOT-23",
        )
        c_specs = [
            ComponentSpecification("voltage", 60.0, "V", "60V"),
            ComponentSpecification("current", 0.30, "A", "300mA"),
        ]

        res = ComponentAlternativesEngine.evaluate_alternative(primary, p_specs, candidate, c_specs)
        self.assertEqual(res.compatibility, CompatibilityLevel.PIN_COMPATIBLE)
        self.assertTrue(res.is_acceptable_substitute())
        self.assertGreaterEqual(res.compatibility_score, 0.8)

        # Candidate with package mismatch -> INCOMPATIBLE or ELECTRICAL_COMPATIBLE
        candidate_dfn = CanonicalComponent(
            desk_id="comp_bjt_3",
            manufacturer_name="Infineon",
            normalized_manufacturer="Infineon",
            mpn="BSS138_DFN",
            normalized_mpn="BSS138_DFN",
            category="Transistors",
            description="50V MOSFET",
            package="DFN1006",
        )
        res_pkg_mismatch = ComponentAlternativesEngine.evaluate_alternative(primary, p_specs, candidate_dfn, p_specs)
        self.assertFalse(res_pkg_mismatch.is_acceptable_substitute())
        self.assertTrue(any("Package mismatch" in v for v in res_pkg_mismatch.violations))

    def test_procurement_bom_generation(self):
        reg = SupplierRegistry()
        reg.register(LcscSupplierProvider())

        parts = [
            {"ref": "R1", "mpn": "0402WGF1001TCE", "package": "0402"},
            {"ref": "R2", "mpn": "0402WGF1001TCE", "package": "0402"},
            {"ref": "U1", "mpn": "TPS62840DLCR", "package": "VSON-8"},
        ]

        report = ProcurementEngine.build_procurement_bom(parts, reg, batch_quantity=10)
        self.assertEqual(report.batch_quantity, 10)
        self.assertEqual(report.total_unique_lines, 2)
        self.assertEqual(report.total_components_placed, 30)  # (2 resistors + 1 IC) * 10
        self.assertGreater(report.total_extended_cost, 0.0)

        # Export CSV test
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            csv_path = tmp.name

        try:
            report.export_csv(csv_path)
            self.assertTrue(os.path.exists(csv_path))
            with open(csv_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("TPS62840DLCR", content)
            self.assertIn("0402WGF1001TCE", content)
            self.assertIn("LCSC", content)
        finally:
            if os.path.exists(csv_path):
                os.remove(csv_path)


if __name__ == "__main__":
    unittest.main()
