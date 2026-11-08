"""
Supplier Provider Abstract Interface.
Establishes the permanent, supplier-agnostic contract for all electronic component distributors.
"""

from __future__ import annotations

import abc
from typing import Any, Dict, List, Optional, Tuple

from desk.component_intelligence.suppliers.capabilities import SupplierCapabilities
from desk.component_intelligence.suppliers.models import SupplierOffer


class SupplierProvider(abc.ABC):
    """Abstract base class for all commercial supplier adapters."""

    def __init__(self, supplier_id: str, name: str, capabilities: Optional[SupplierCapabilities] = None):
        self.supplier_id = supplier_id
        self.name = name
        self.capabilities = capabilities or SupplierCapabilities()
        self._enabled: bool = True

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled

    @abc.abstractmethod
    def search_components(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 20,
    ) -> List[SupplierOffer]:
        """Searches supplier catalog for parts matching query keywords or MPNs."""
        pass

    @abc.abstractmethod
    def get_component(self, supplier_part_number: str) -> Optional[SupplierOffer]:
        """Retrieves complete product details for an exact supplier SKU."""
        pass

    @abc.abstractmethod
    def get_offers(self, mpn: str) -> List[SupplierOffer]:
        """Retrieves all commercial offers for an exact Manufacturer Part Number."""
        pass

    def get_availability(self, supplier_part_number: str) -> Tuple[int, bool]:
        """Retrieves current stock quantity and in-stock boolean flag."""
        offer = self.get_component(supplier_part_number)
        if offer:
            return offer.stock, offer.stock > 0
        return 0, False

    def get_pricing(self, supplier_part_number: str, quantity: int = 1) -> Optional[float]:
        """Calculates unit price for a requested purchase quantity."""
        offer = self.get_component(supplier_part_number)
        if offer:
            return offer.get_price_for_quantity(quantity)
        return None
