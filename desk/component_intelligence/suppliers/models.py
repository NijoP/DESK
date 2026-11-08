"""
Normalized Supplier Commercial Models.
Maintains supplier offers, pricing tiers, and stock snapshots strictly separate
from the canonical component identity.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PriceBreak:
    """Pricing break tier for volume orders."""
    quantity: int
    unit_price: float
    currency: str = "USD"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "quantity": self.quantity,
            "unit_price": self.unit_price,
            "currency": self.currency,
        }


@dataclass
class SupplierOffer:
    """
    Commercial catalog entry and live offer from an external distributor.
    Does NOT own canonical component identity.
    """
    supplier_id: str          # e.g., "lcsc", "mouser", "digikey"
    supplier_name: str        # e.g., "LCSC Electronics"
    sku: str                  # Supplier part number, e.g. "C11702"
    canonical_desk_id: str    # Foreign key referencing CanonicalComponent.desk_id
    manufacturer_name: str    # Manufacturer as reported by supplier
    mpn: str                  # MPN as reported by supplier
    product_url: str = ""
    datasheet_url: Optional[str] = None
    description: str = ""
    package: str = ""
    stock: int = 0
    currency: str = "USD"
    unit_price: float = 0.0
    price_breaks: List[PriceBreak] = field(default_factory=list)
    moq: int = 1
    lead_time_days: Optional[int] = None
    last_checked_ts: float = field(default_factory=time.time)
    raw_payload: Dict[str, Any] = field(default_factory=dict)

    def get_price_for_quantity(self, qty: int) -> float:
        """Determines best unit price for a requested purchase quantity."""
        if not self.price_breaks:
            return self.unit_price

        # Sort price breaks descending by quantity threshold
        sorted_breaks = sorted(self.price_breaks, key=lambda p: p.quantity, reverse=True)
        for pb in sorted_breaks:
            if qty >= pb.quantity:
                return pb.unit_price
        return self.unit_price

    def to_dict(self) -> Dict[str, Any]:
        return {
            "supplier_id": self.supplier_id,
            "supplier_name": self.supplier_name,
            "sku": self.sku,
            "canonical_desk_id": self.canonical_desk_id,
            "manufacturer_name": self.manufacturer_name,
            "mpn": self.mpn,
            "product_url": self.product_url,
            "datasheet_url": self.datasheet_url,
            "description": self.description,
            "package": self.package,
            "stock": self.stock,
            "currency": self.currency,
            "unit_price": self.unit_price,
            "price_breaks": [pb.to_dict() for pb in self.price_breaks],
            "moq": self.moq,
            "lead_time_days": self.lead_time_days,
            "last_checked_ts": self.last_checked_ts,
        }
