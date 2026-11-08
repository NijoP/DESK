"""
EDA Library Provider Registry.
"""

from __future__ import annotations

import logging
import threading
from typing import Dict, List, Optional

from desk.component_intelligence.eda.base import EDALibraryProvider
from desk.component_intelligence.eda.models import EDAAsset

logger = logging.getLogger("desk.component_intelligence.eda")


class EDARegistry:
    """Registry maintaining active EDA library providers."""
    _instance: Optional["EDARegistry"] = None

    def __init__(self) -> None:
        self._providers: Dict[str, EDALibraryProvider] = {}
        self._lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "EDARegistry":
        if cls._instance is None:
            cls._instance = EDARegistry()
        return cls._instance

    def register(self, provider: EDALibraryProvider) -> None:
        """Registers an EDA provider."""
        with self._lock:
            if provider.provider_id in self._providers:
                raise ValueError(f"EDA provider '{provider.provider_id}' is already registered.")
            self._providers[provider.provider_id] = provider

    def get_provider(self, provider_id: str) -> Optional[EDALibraryProvider]:
        with self._lock:
            return self._providers.get(provider_id)

    def list_providers(self, enabled_only: bool = True) -> List[EDALibraryProvider]:
        with self._lock:
            if enabled_only:
                return [p for p in self._providers.values() if p.is_enabled]
            return list(self._providers.values())

    def search_symbols(self, query: str) -> List[EDAAsset]:
        results: List[EDAAsset] = []
        for p in self.list_providers(enabled_only=True):
            if p.capabilities.symbols:
                try:
                    results.extend(p.search_symbols(query))
                except Exception as e:
                    logger.warning("Error searching symbols in %s: %s", p.provider_id, e)
        return results

    def search_footprints(self, query: str) -> List[EDAAsset]:
        results: List[EDAAsset] = []
        for p in self.list_providers(enabled_only=True):
            if p.capabilities.footprints:
                try:
                    results.extend(p.search_footprints(query))
                except Exception as e:
                    logger.warning("Error searching footprints in %s: %s", p.provider_id, e)
        return results
