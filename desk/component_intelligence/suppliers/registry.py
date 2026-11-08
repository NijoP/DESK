"""
Supplier Provider Registry.
Manages registration, discovery, and isolated execution across supplier adapters.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, List, Optional

from desk.component_intelligence.suppliers.base import SupplierProvider
from desk.component_intelligence.suppliers.models import SupplierOffer

logger = logging.getLogger("desk.component_intelligence.suppliers")


class SupplierRegistry:
    """Registry maintaining all available supplier providers."""
    _instance: Optional["SupplierRegistry"] = None

    def __init__(self) -> None:
        self._providers: Dict[str, SupplierProvider] = {}
        self._lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "SupplierRegistry":
        if cls._instance is None:
            cls._instance = SupplierRegistry()
        return cls._instance

    def register(self, provider: SupplierProvider) -> None:
        """Registers a supplier provider. Raises ValueError on duplicate supplier_id."""
        with self._lock:
            if provider.supplier_id in self._providers:
                raise ValueError(
                    f"Supplier provider with ID '{provider.supplier_id}' is already registered."
                )
            self._providers[provider.supplier_id] = provider

    def unregister(self, supplier_id: str) -> None:
        """Unregisters a supplier provider."""
        with self._lock:
            self._providers.pop(supplier_id, None)

    def get_provider(self, supplier_id: str) -> Optional[SupplierProvider]:
        """Retrieves a provider by ID."""
        with self._lock:
            return self._providers.get(supplier_id)

    def list_providers(self, enabled_only: bool = True) -> List[SupplierProvider]:
        """Returns registered providers."""
        with self._lock:
            if enabled_only:
                return [p for p in self._providers.values() if p.is_enabled]
            return list(self._providers.values())

    def search_all(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        limit_per_supplier: int = 10,
    ) -> List[SupplierOffer]:
        """Queries all enabled supplier providers, isolating errors so one failure doesn't block others."""
        all_offers: List[SupplierOffer] = []
        providers = self.list_providers(enabled_only=True)

        for p in providers:
            if not p.capabilities.search:
                continue
            try:
                offers = p.search_components(query, filters=filters, limit=limit_per_supplier)
                all_offers.extend(offers)
            except Exception as e:
                logger.warning("Error querying supplier '%s' for '%s': %s", p.supplier_id, query, e)

        return all_offers

    def get_offers_for_mpn(self, mpn: str) -> List[SupplierOffer]:
        """Queries all enabled suppliers for offers matching an exact MPN."""
        all_offers: List[SupplierOffer] = []
        providers = self.list_providers(enabled_only=True)

        for p in providers:
            try:
                offers = p.get_offers(mpn)
                all_offers.extend(offers)
            except Exception as e:
                logger.warning("Error querying offers from '%s' for MPN '%s': %s", p.supplier_id, mpn, e)

        return all_offers
