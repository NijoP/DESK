"""
Unit tests for Supplier Capabilities, Base Contract, and Supplier Registry.
"""

import unittest
from typing import Any, Dict, List, Optional

from desk.component_intelligence.suppliers.base import SupplierProvider
from desk.component_intelligence.suppliers.capabilities import SupplierCapabilities
from desk.component_intelligence.suppliers.models import PriceBreak, SupplierOffer
from desk.component_intelligence.suppliers.registry import SupplierRegistry


class MockSupplierProvider(SupplierProvider):
    def __init__(self, supplier_id: str, name: str, should_fail: bool = False):
        super().__init__(supplier_id, name)
        self.should_fail = should_fail

    def search_components(self, query: str, filters: Optional[Dict[str, Any]] = None, limit: int = 20) -> List[SupplierOffer]:
        if self.should_fail:
            raise ConnectionError("Mock supplier network timeout")
        return [
            SupplierOffer(
                supplier_id=self.supplier_id,
                supplier_name=self.name,
                sku=f"SKU_{query}",
                canonical_desk_id=f"comp_{query}",
                manufacturer_name="TestMfr",
                mpn=query,
                stock=500,
                unit_price=0.25,
            )
        ]

    def get_component(self, supplier_part_number: str) -> Optional[SupplierOffer]:
        return None

    def get_offers(self, mpn: str) -> List[SupplierOffer]:
        return self.search_components(mpn)


class TestSupplierSystem(unittest.TestCase):
    def test_supplier_capabilities(self):
        caps = SupplierCapabilities(search=True, ordering=False)
        self.assertTrue(caps.search)
        self.assertFalse(caps.ordering)
        d = caps.to_dict()
        self.assertIn("search", d)

    def test_price_break_tiers(self):
        offer = SupplierOffer(
            supplier_id="test_supp",
            supplier_name="Test Supplier",
            sku="T123",
            canonical_desk_id="c1",
            manufacturer_name="Mfr",
            mpn="MPN1",
            stock=1000,
            unit_price=1.00,
            price_breaks=[
                PriceBreak(quantity=1, unit_price=1.00),
                PriceBreak(quantity=10, unit_price=0.80),
                PriceBreak(quantity=100, unit_price=0.50),
            ],
        )
        self.assertEqual(offer.get_price_for_quantity(1), 1.00)
        self.assertEqual(offer.get_price_for_quantity(5), 1.00)
        self.assertEqual(offer.get_price_for_quantity(10), 0.80)
        self.assertEqual(offer.get_price_for_quantity(50), 0.80)
        self.assertEqual(offer.get_price_for_quantity(150), 0.50)

    def test_registry_registration_and_duplicate_rejection(self):
        reg = SupplierRegistry()
        p1 = MockSupplierProvider("supp_a", "Supplier A")
        reg.register(p1)
        self.assertEqual(reg.get_provider("supp_a"), p1)

        # Duplicate registration must raise ValueError
        with self.assertRaises(ValueError):
            reg.register(MockSupplierProvider("supp_a", "Duplicate"))

    def test_registry_error_isolation(self):
        reg = SupplierRegistry()
        good_p = MockSupplierProvider("good_supp", "Good Supplier", should_fail=False)
        failing_p = MockSupplierProvider("fail_supp", "Failing Supplier", should_fail=True)

        reg.register(good_p)
        reg.register(failing_p)

        # Querying all suppliers must still return good provider's results without raising error
        results = reg.search_all("TPS62840")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].supplier_id, "good_supp")


if __name__ == "__main__":
    unittest.main()
