"""
LCSC Supplier Provider Implementation.
Integrates LCSC catalog and inventory search into the supplier-agnostic DESK core.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from desk.component_intelligence.suppliers.base import SupplierProvider
from desk.component_intelligence.suppliers.capabilities import SupplierCapabilities
from desk.component_intelligence.suppliers.models import SupplierOffer
from desk.component_intelligence.suppliers.providers.lcsc.client import LcscApiClient
from desk.component_intelligence.suppliers.providers.lcsc.mapper import LcscDataMapper


class LcscSupplierProvider(SupplierProvider):
    """Supplier adapter for LCSC Electronics."""

    def __init__(
        self,
        client: Optional[LcscApiClient] = None,
        capabilities: Optional[SupplierCapabilities] = None,
    ) -> None:
        caps = capabilities or SupplierCapabilities(
            search=True,
            product_details=True,
            pricing=True,
            inventory=True,
            datasheet_links=True,
            ordering=False,
            package_filter=True,
            category_filter=True,
        )
        super().__init__(supplier_id="lcsc", name="LCSC Electronics", capabilities=caps)
        self.client = client or LcscApiClient()

    def search_components(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 20,
    ) -> List[SupplierOffer]:
        items = self.client.search_products(query, limit=limit)
        offers: List[SupplierOffer] = []
        for it in items:
            offer = LcscDataMapper.to_supplier_offer(it)
            # Optional package filter
            if filters and "package" in filters:
                req_pkg = str(filters["package"]).upper()
                if offer.package.upper() != req_pkg:
                    continue
            offers.append(offer)
        return offers

    def get_component(self, supplier_part_number: str) -> Optional[SupplierOffer]:
        item = self.client.get_product_detail(supplier_part_number)
        if item:
            return LcscDataMapper.to_supplier_offer(item)
        return None

    def get_offers(self, mpn: str) -> List[SupplierOffer]:
        # Search exact MPN
        results = self.search_components(mpn, limit=10)
        clean_mpn = mpn.strip().upper()
        exact_matches = [o for o in results if o.mpn.strip().upper() == clean_mpn]
        return exact_matches if exact_matches else results
