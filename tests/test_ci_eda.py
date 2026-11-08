"""
Unit tests for EDA Provider Layer and Local Offline Library Provider.
"""

import unittest

from desk.component_intelligence.eda.models import AssetType, EDAAsset
from desk.component_intelligence.eda.providers.local import LocalEDALibraryProvider
from desk.component_intelligence.eda.registry import EDARegistry


class TestEDALibrary(unittest.TestCase):
    def test_local_offline_eda_provider(self):
        local_p = LocalEDALibraryProvider()
        self.assertEqual(local_p.provider_id, "local")
        self.assertTrue(local_p.capabilities.symbols)
        self.assertTrue(local_p.capabilities.footprints)

        # Search symbols from real library/pins/ cache
        symbols = local_p.search_symbols("TPS62840")
        if symbols:
            sym = symbols[0]
            self.assertEqual(sym.asset_type, AssetType.SYMBOL)
            self.assertGreater(sym.pin_count, 0)
            self.assertTrue(len(sym.pins) > 0)

        # Search footprints from real library/devices.json cache
        footprints = local_p.search_footprints("R0402")
        self.assertGreaterEqual(len(footprints), 1)
        self.assertEqual(footprints[0].asset_name, "R0402")

    def test_eda_registry(self):
        reg = EDARegistry()
        local_p = LocalEDALibraryProvider()
        reg.register(local_p)

        self.assertEqual(reg.get_provider("local"), local_p)
        # Duplicate rejection
        with self.assertRaises(ValueError):
            reg.register(LocalEDALibraryProvider())


if __name__ == "__main__":
    unittest.main()
