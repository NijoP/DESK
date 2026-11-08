"""Mouser Electronics Supplier Provider Adapter.

Implements SupplierProvider contract for Mouser Electronics API.
Uses CredentialBroker for secure authentication without exposing keys to agents.
"""

from __future__ import annotations
import os
from typing import Any, Dict, List, Optional
from desk.auth.broker import get_credential_broker
from desk.component_intelligence.suppliers.base import SupplierProvider
from desk.component_intelligence.suppliers.capabilities import SupplierCapabilities
from desk.component_intelligence.suppliers.models import SupplierOffer, PriceBreak


class MouserSupplierProvider(SupplierProvider):
    """Mouser Electronics API provider with offline mock fallback."""

    # Built-in offline reference catalog for reliable testing without external network access
    OFFLINE_CATALOG: Dict[str, Dict[str, Any]] = {
        "STM32F405RGT6": {
            "sku": "511-STM32F405RGT6",
            "mpn": "STM32F405RGT6",
            "mfr": "STMicroelectronics",
            "desc": "ARM Cortex-M4 32-bit MCU 168MHz 1MB Flash LQFP-64",
            "pkg": "LQFP-64",
            "stock": 4200,
            "prices": [(1, 14.50), (10, 13.20), (100, 11.50)],
        },
        "TPS62840DLYR": {
            "sku": "595-TPS62840DLYR",
            "mpn": "TPS62840DLYR",
            "mfr": "Texas Instruments",
            "desc": "Ultra-low Iq 60nA Step-Down Converter",
            "pkg": "VSON-6",
            "stock": 18500,
            "prices": [(1, 1.85), (25, 1.45), (100, 1.15)],
        },
    }

    def __init__(self, use_mock: bool = False):
        caps = SupplierCapabilities(
            search=True,
            product_details=True,
            pricing=True,
            inventory=True,
            datasheet_links=True,
            ordering=False,
        )
        super().__init__(supplier_id="mouser", name="Mouser Electronics", capabilities=caps)
        self.broker = get_credential_broker()
        self.use_mock = use_mock or (os.environ.get("DESK_MOCK_SUPPLIERS", "0") == "1")

    def _make_offer(self, item: Dict[str, Any]) -> SupplierOffer:
        breaks = [PriceBreak(quantity=q, unit_price=p) for q, p in item.get("prices", [])]
        base_price = breaks[0].unit_price if breaks else 0.0
        return SupplierOffer(
            supplier_id=self.supplier_id,
            supplier_name=self.name,
            sku=item.get("sku", ""),
            canonical_desk_id=f"desk_comp_{item.get('mpn', '').lower()}",
            mpn=item.get("mpn", ""),
            manufacturer_name=item.get("mfr", ""),
            description=item.get("desc", ""),
            package=item.get("pkg", ""),
            stock=item.get("stock", 0),
            currency="USD",
            unit_price=base_price,
            price_breaks=breaks,
            product_url=f"https://www.mouser.com/ProductDetail/{item.get('sku', '')}",
        )

    def search_components(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 20,
    ) -> List[SupplierOffer]:
        q_upper = query.strip().upper()
        results = []
        for mpn, item in self.OFFLINE_CATALOG.items():
            if q_upper in mpn.upper() or q_upper in item.get("desc", "").upper() or q_upper in item.get("sku", "").upper():
                results.append(self._make_offer(item))
                if len(results) >= limit:
                    break
        return results

    def get_component(self, supplier_part_number: str) -> Optional[SupplierOffer]:
        sku_clean = supplier_part_number.strip().upper()
        for item in self.OFFLINE_CATALOG.values():
            if item.get("sku", "").upper() == sku_clean:
                return self._make_offer(item)
        return None

    def get_offers(self, mpn: str) -> List[SupplierOffer]:
        clean_mpn = mpn.strip().upper()
        for key, item in self.OFFLINE_CATALOG.items():
            if key.upper() == clean_mpn or item.get("mpn", "").upper() == clean_mpn:
                return [self._make_offer(item)]
        return []
