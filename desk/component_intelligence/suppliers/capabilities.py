"""
Supplier Capabilities Declarations.
Explicitly declares which operations a given supplier adapter supports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class SupplierCapabilities:
    """Explicit capability declaration for a supplier provider."""
    search: bool = True
    product_details: bool = True
    pricing: bool = True
    inventory: bool = True
    datasheet_links: bool = True
    ordering: bool = False
    package_filter: bool = False
    category_filter: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "search": self.search,
            "product_details": self.product_details,
            "pricing": self.pricing,
            "inventory": self.inventory,
            "datasheet_links": self.datasheet_links,
            "ordering": self.ordering,
            "package_filter": self.package_filter,
            "category_filter": self.category_filter,
        }
