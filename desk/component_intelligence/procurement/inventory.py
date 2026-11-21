"""Inventory classification for supplier offers (roadmap I-5).

A pure, offline function: given one SupplierOffer, the quantity the build needs and the current
time, return one of seven states plus the limitations behind it. No network, no clock unless the
caller omits ``now``.

The rule the Captain set: an unavailable or unverified result is never in stock. Concretely:

- only offers whose ``availability_source`` is in ``VERIFIED_SOURCES`` (a public live endpoint read
  by DESK, or a browser-agent evidence record) can reach IN_STOCK_CONFIRMED or LOW_STOCK;
- an offline fixture, a library seed, a missing stock figure, a missing or future timestamp and a
  snapshot older than ``max_age_days`` all give STOCK_UNKNOWN, and the reason is written into
  ``limitations`` so the report can say what was not verified instead of inventing availability.
"""

from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from desk.component_intelligence.suppliers.models import VERIFIED_SOURCES, SupplierOffer


class InventoryState(str, enum.Enum):
    IN_STOCK_CONFIRMED = "IN_STOCK_CONFIRMED"
    LOW_STOCK = "LOW_STOCK"
    OUT_OF_STOCK = "OUT_OF_STOCK"
    BACKORDERED = "BACKORDERED"
    DISCONTINUED = "DISCONTINUED"
    STOCK_UNKNOWN = "STOCK_UNKNOWN"
    PRICE_UNAVAILABLE = "PRICE_UNAVAILABLE"


class Lifecycle(str, enum.Enum):
    ACTIVE = "ACTIVE"
    NRND = "NRND"
    DISCONTINUED = "DISCONTINUED"
    UNKNOWN = "UNKNOWN"


# Supplier wording -> lifecycle. Matched on the lower-cased, stripped text; unknown wording stays
# UNKNOWN (never silently ACTIVE). "normal" is what LCSC's public detail JSON shows in productCycle.
_LIFECYCLE_WORDS: Dict[str, Lifecycle] = {
    "active": Lifecycle.ACTIVE, "normal": Lifecycle.ACTIVE, "in production": Lifecycle.ACTIVE,
    "production": Lifecycle.ACTIVE, "new": Lifecycle.ACTIVE,
    "nrnd": Lifecycle.NRND, "not recommended for new designs": Lifecycle.NRND,
    "not recommended": Lifecycle.NRND, "last time buy": Lifecycle.NRND, "ltb": Lifecycle.NRND,
    "discontinued": Lifecycle.DISCONTINUED, "obsolete": Lifecycle.DISCONTINUED,
    "eol": Lifecycle.DISCONTINUED, "end of life": Lifecycle.DISCONTINUED,
    "end-of-life": Lifecycle.DISCONTINUED, "discontinue": Lifecycle.DISCONTINUED,
}

DEFAULT_MAX_AGE_DAYS = 7.0          # same freshness window as V4 procurement verification
DEFAULT_LOW_STOCK_MULTIPLIER = 2.0  # stock below 2x the build quantity is LOW_STOCK

# Stock states an offer may be selected from without a client permission flag.
SELECTABLE_STOCK_STATES = (InventoryState.IN_STOCK_CONFIRMED, InventoryState.LOW_STOCK)


def normalize_lifecycle(text: str) -> Lifecycle:
    t = (text or "").strip().lower()
    if not t:
        return Lifecycle.UNKNOWN
    return _LIFECYCLE_WORDS.get(t, Lifecycle.UNKNOWN)


@dataclass
class InventoryAssessment:
    """Classification of one offer for one required quantity."""
    state: InventoryState          # overall state (PRICE_UNAVAILABLE when stock is fine but no price)
    stock_state: InventoryState    # stock-only state (never PRICE_UNAVAILABLE)
    required_quantity: int
    stock: Optional[int]           # None when no verified figure exists
    covers_required: bool          # verified stock >= required quantity
    price_available: bool
    lifecycle: Lifecycle
    age_days: Optional[float]
    limitations: List[str] = field(default_factory=list)

    @property
    def in_stock(self) -> bool:
        """True only for verified stock that covers the required quantity."""
        return self.stock_state in SELECTABLE_STOCK_STATES and self.covers_required

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state.value,
            "stock_state": self.stock_state.value,
            "required_quantity": self.required_quantity,
            "stock": self.stock,
            "covers_required": self.covers_required,
            "price_available": self.price_available,
            "lifecycle": self.lifecycle.value,
            "age_days": None if self.age_days is None else round(self.age_days, 2),
            "limitations": list(self.limitations),
        }


def classify_offer(
    offer: SupplierOffer,
    required_quantity: int = 1,
    now: Optional[float] = None,
    max_age_days: float = DEFAULT_MAX_AGE_DAYS,
    low_stock_multiplier: float = DEFAULT_LOW_STOCK_MULTIPLIER,
) -> InventoryAssessment:
    """Classify ``offer`` for ``required_quantity`` units. Pure; ``now`` defaults to time.time()."""
    now = time.time() if now is None else now
    req = max(1, int(required_quantity))
    lims: List[str] = []
    lifecycle = normalize_lifecycle(offer.lifecycle)
    price_ok = offer.price_available()
    who = f"{offer.supplier_name or offer.supplier_id} {offer.sku}".strip()

    ts = offer.last_checked_ts or 0.0
    age = (now - ts) / 86400.0 if ts > 0 else None

    def done(stock_state: InventoryState, stock: Optional[int], covers: bool) -> InventoryAssessment:
        state = stock_state
        if stock_state in SELECTABLE_STOCK_STATES and not price_ok:
            state = InventoryState.PRICE_UNAVAILABLE
            lims.append(f"{who}: stock verified but no price was shown; cost is not known.")
        elif not price_ok:
            lims.append(f"{who}: no price shown.")
        return InventoryAssessment(state, stock_state, req, stock, covers, price_ok, lifecycle, age, lims)

    if offer.lifecycle and lifecycle is Lifecycle.UNKNOWN:
        lims.append(f"{who}: lifecycle text '{offer.lifecycle}' not recognised; treated as unknown, not active.")
    if lifecycle is Lifecycle.NRND:
        lims.append(f"{who}: not recommended for new designs ({offer.lifecycle}).")

    # Discontinued wins over any stock figure: residual stock does not make an EOL part a good pick.
    if lifecycle is Lifecycle.DISCONTINUED:
        if offer.stock_known and offer.stock > 0:
            lims.append(f"{who}: discontinued ({offer.lifecycle}); {offer.stock} units of residual stock ignored.")
        else:
            lims.append(f"{who}: discontinued ({offer.lifecycle}).")
        return done(InventoryState.DISCONTINUED, offer.stock if offer.stock_known else None, False)

    # Provenance gate: nothing unverified is ever in stock.
    if offer.availability_source not in VERIFIED_SOURCES:
        lims.append(
            f"{who}: availability source is '{offer.availability_source}', not a live supplier read or "
            f"browser-agent evidence; stock is not verified."
        )
        return done(InventoryState.STOCK_UNKNOWN, None, False)
    if age is None:
        lims.append(f"{who}: no verification timestamp; stock is not verified.")
        return done(InventoryState.STOCK_UNKNOWN, None, False)
    if age < -(5.0 / 1440.0):  # more than 5 minutes in the future: clock or record error
        lims.append(f"{who}: verification timestamp is in the future; stock is not verified.")
        return done(InventoryState.STOCK_UNKNOWN, None, False)
    if age > max_age_days:
        lims.append(f"{who}: stock snapshot is {age:.1f} days old (limit {max_age_days:g}); re-verify.")
        return done(InventoryState.STOCK_UNKNOWN, None, False)
    if not offer.stock_known:
        if offer.backorder:
            lims.append(f"{who}: offered on backorder; no stock figure shown.")
            return done(InventoryState.BACKORDERED, None, False)
        lims.append(f"{who}: the supplier page showed no stock figure.")
        return done(InventoryState.STOCK_UNKNOWN, None, False)

    stock = max(0, int(offer.stock))
    covers = stock >= req
    if offer.backorder and not covers:
        lt = f", lead time {offer.lead_time_days} days" if offer.lead_time_days else ""
        lims.append(f"{who}: {stock} in stock for {req} required; the rest is on backorder{lt}.")
        return done(InventoryState.BACKORDERED, stock, False)
    if stock == 0:
        lims.append(f"{who}: out of stock.")
        return done(InventoryState.OUT_OF_STOCK, 0, False)
    if stock < req * low_stock_multiplier:
        if covers:
            lims.append(f"{who}: {stock} in stock covers {req} required but with under {low_stock_multiplier:g}x margin.")
        else:
            lims.append(f"{who}: only {stock} in stock for {req} required.")
        return done(InventoryState.LOW_STOCK, stock, covers)
    return done(InventoryState.IN_STOCK_CONFIRMED, stock, True)
