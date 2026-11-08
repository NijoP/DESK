"""
Unit tests for LCSC Provider, API Client, and Data Mapper.
"""

import unittest

from desk.component_intelligence.suppliers.providers.lcsc.client import LcscApiClient
from desk.component_intelligence.suppliers.providers.lcsc.mapper import LcscDataMapper
from desk.component_intelligence.suppliers.providers.lcsc.models import LcscProductItem
from desk.component_intelligence.suppliers.providers.lcsc.provider import LcscSupplierProvider


class TestLcscProvider(unittest.TestCase):
    def setUp(self):
        # Force offline fixtures mode for deterministic test execution
        self.client = LcscApiClient(use_offline_fixtures=True)
        self.provider = LcscSupplierProvider(client=self.client)

    def test_search_offline_fixtures(self):
        results = self.provider.search_components("TPS62840")
        self.assertGreaterEqual(len(results), 1)
        offer = results[0]
        self.assertEqual(offer.supplier_id, "lcsc")
        self.assertEqual(offer.sku, "C347222")
        self.assertEqual(offer.mpn, "TPS62840DLCR")
        self.assertEqual(offer.manufacturer_name, "Texas Instruments")
        self.assertEqual(offer.package, "VSON-8")
        self.assertGreater(offer.stock, 0)
        self.assertEqual(offer.currency, "USD")

    def test_get_component_by_lcsc_code(self):
        offer = self.provider.get_component("C11702")
        self.assertIsNotNone(offer)
        self.assertEqual(offer.mpn, "0402WGF1001TCE")
        self.assertEqual(offer.manufacturer_name, "Uni-Royal")
        self.assertEqual(offer.package, "0402")
        self.assertGreaterEqual(len(offer.price_breaks), 3)

    def test_lcsc_data_mapper(self):
        raw_dict = {
            "productCode": "C9999",
            "productModel": "TEST-MPN-100",
            "brandNameEn": "STMicroelectronics",
            "catalogName": "Microcontrollers",
            "parentCatalogName": "Embedded",
            "packageDetail": "LQFP-64",
            "stockNumber": 5000,
            "productPriceList": [
                {"ladder": 1, "productPrice": 2.50, "currency": "USD"},
                {"ladder": 10, "productPrice": 2.00, "currency": "USD"},
            ],
            "pdfUrl": "https://example.com/ds.pdf",
            "productDescEn": "32-bit MCU 64KB Flash",
        }
        item = LcscProductItem.from_dict(raw_dict)
        canon = LcscDataMapper.to_canonical_component(item)
        offer = LcscDataMapper.to_supplier_offer(item)

        self.assertEqual(canon.normalized_manufacturer, "STMicroelectronics")
        self.assertEqual(canon.normalized_mpn, "TEST-MPN-100")
        self.assertEqual(offer.sku, "C9999")
        self.assertEqual(offer.stock, 5000)
        self.assertEqual(offer.get_price_for_quantity(1), 2.50)
        self.assertEqual(offer.get_price_for_quantity(15), 2.00)

    def test_package_filter(self):
        # Filter 0402 package
        results = self.provider.search_components("Resistor", filters={"package": "0402"})
        for o in results:
            self.assertEqual(o.package.upper(), "0402")


if __name__ == "__main__":
    unittest.main()
