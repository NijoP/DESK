"""
EDA Provider Abstract Base Contract.
"""

from __future__ import annotations

import abc
from typing import Any, Dict, List, Optional

from desk.component_intelligence.eda.capabilities import EDACapabilities
from desk.component_intelligence.eda.models import EDAAsset


class EDALibraryProvider(abc.ABC):
    """Abstract interface for EDA library adapters (EasyEDA, KiCad, Local)."""

    def __init__(self, provider_id: str, name: str, capabilities: Optional[EDACapabilities] = None):
        self.provider_id = provider_id
        self.name = name
        self.capabilities = capabilities or EDACapabilities()
        self._enabled: bool = True

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled

    @abc.abstractmethod
    def search_symbols(self, query: str) -> List[EDAAsset]:
        """Searches CAD symbols matching query."""
        pass

    @abc.abstractmethod
    def search_footprints(self, query: str) -> List[EDAAsset]:
        """Searches CAD footprints matching query."""
        pass

    @abc.abstractmethod
    def get_asset(self, asset_id: str) -> Optional[EDAAsset]:
        """Retrieves an exact CAD asset by ID."""
        pass
