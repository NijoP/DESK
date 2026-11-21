"""
Normalized Supplier Commercial Models.
Maintains supplier offers, pricing tiers, and stock snapshots strictly separate
from the canonical component identity.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Where an offer's stock and price came from. Only the VERIFIED_SOURCES may ever be classified
# as in stock (desk.component_intelligence.procurement.inventory); everything else is STOCK_UNKNOWN.
SOURCE_LIVE_API = "live_api"              # DESK fetched it from a public supplier endpoint just now
SOURCE_AGENT_EVIDENCE = "agent_evidence"  # a browser-capable agent read it on the supplier's page
SOURCE_FIXTURE = "fixture"                # offline test/demo catalogue - never real availability
SOURCE_SEED = "seed"                      # imported from library/devices.json - identity only
SOURCE_UNVERIFIED = "unverified"          # anything else (default)
VERIFIED_SOURCES = (SOURCE_LIVE_API, SOURCE_AGENT_EVIDENCE)


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
    # -- availability provenance (I-5): who saw this stock/price, where and how ----------
    availability_source: str = SOURCE_UNVERIFIED  # one of the SOURCE_* constants above
    stock_known: bool = True      # False when the supplier showed no stock figure at all
    lifecycle: str = ""           # as shown by the supplier: "active", "NRND", "discontinued", ...
    backorder: bool = False       # supplier offers the part on backorder / pre-sale
    footprint: str = ""           # land-pattern name when the supplier shows one
    specs: Dict[str, Any] = field(default_factory=dict)  # electrical + mechanical parameters
    alternative_for: str = ""     # MPN this offer was proposed as an alternative to
    assembly_class: str = ""      # JLCPCB parts library class (Basic/Preferred/Extended) if shown

    def price_available(self) -> bool:
        """True when the offer carries at least one real (positive) unit price."""
        return self.unit_price > 0 or any(pb.unit_price > 0 for pb in self.price_breaks)

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
            "availability_source": self.availability_source,
            "stock_known": self.stock_known,
            "lifecycle": self.lifecycle,
            "backorder": self.backorder,
            "footprint": self.footprint,
            "specs": dict(self.specs),
            "alternative_for": self.alternative_for,
            "assembly_class": self.assembly_class,
        }
