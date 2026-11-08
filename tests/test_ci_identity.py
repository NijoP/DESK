"""
Unit tests for Canonical Component Identity and Resolver.
"""

import unittest

from desk.component_intelligence.identity.models import (
    CanonicalComponent,
    DatasheetReference,
    IdentityVerificationStatus,
    LifecycleStatus,
)
from desk.component_intelligence.identity.resolver import ComponentIdentityResolver


class TestComponentIdentity(unittest.TestCase):
    def test_manufacturer_normalization(self):
        # TI variations
        self.assertEqual(ComponentIdentityResolver.normalize_manufacturer("TI"), "Texas Instruments")
        self.assertEqual(ComponentIdentityResolver.normalize_manufacturer("Texas Instruments Inc."), "Texas Instruments")
        self.assertEqual(ComponentIdentityResolver.normalize_manufacturer("Texas Instruments Incorporated"), "Texas Instruments")

        # ST variations
        self.assertEqual(ComponentIdentityResolver.normalize_manufacturer("STM"), "STMicroelectronics")
        self.assertEqual(ComponentIdentityResolver.normalize_manufacturer("STMicroelectronics Co., Ltd."), "STMicroelectronics")

        # Unknown / Generic with corporate suffix stripping
        self.assertEqual(ComponentIdentityResolver.normalize_manufacturer("Acme Electronics Corp."), "Acme Electronics")
        self.assertEqual(ComponentIdentityResolver.normalize_manufacturer(""), "Generic")

    def test_mpn_normalization(self):
        self.assertEqual(ComponentIdentityResolver.normalize_mpn("tps62840dlcr"), "TPS62840DLCR")
        self.assertEqual(ComponentIdentityResolver.normalize_mpn(" 0402WGF1001TCE "), "0402WGF1001TCE")
        self.assertEqual(ComponentIdentityResolver.normalize_mpn("CL05B104KO5NNNC\u00a0"), "CL05B104KO5NNNC")
        # En-dash / Em-dash normalization
        self.assertEqual(ComponentIdentityResolver.normalize_mpn("STM32F401–CCU6"), "STM32F401-CCU6")

    def test_deterministic_desk_id_generation(self):
        id1 = ComponentIdentityResolver.generate_desk_id("Texas Instruments", "TPS62840DLCR")
        id2 = ComponentIdentityResolver.generate_desk_id("TEXAS INSTRUMENTS", "tps62840dlcr")
        self.assertEqual(id1, id2)
        self.assertTrue(id1.startswith("comp_"))

    def test_resolve_component(self):
        comp = ComponentIdentityResolver.resolve(
            manufacturer="TI Inc.",
            mpn="TPS62840DLCR",
            package="VSON-8",
            description="Ultra-low power buck regulator",
            datasheet_url="https://ti.com/tps62840.pdf",
        )
        self.assertEqual(comp.normalized_manufacturer, "Texas Instruments")
        self.assertEqual(comp.normalized_mpn, "TPS62840DLCR")
        self.assertEqual(comp.package, "VSON-8")
        self.assertIn("Power Management", comp.category)
        self.assertEqual(len(comp.datasheets), 1)

    def test_detect_conflicts(self):
        c1 = ComponentIdentityResolver.resolve("TI", "TPS62840DLCR", package="VSON-8")
        c2 = ComponentIdentityResolver.resolve("TI", "TPS62840DLCR", package="WSON-8")
        conflicts = ComponentIdentityResolver.detect_conflicts(c1, c2)
        self.assertTrue(any("Package conflict" in w for w in conflicts))


if __name__ == "__main__":
    unittest.main()
