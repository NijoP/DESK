"""JLCPCB parts library: assembly compatibility from public evidence (roadmap I-5).

JLCPCB is the assembler, not a primary supplier: its parts library says whether a part can be placed
by JLCPCB SMT assembly, in which class (Basic / Preferred / Extended) and with how much assembly
stock. DESK has no JLCPCB account, and https://jlcpcb.com/robots.txt disallows ``/api`` for every
crawler (checked 2026-11-21), so DESK does not query it. A browser-capable agent reads the public
part page (``https://jlcpcb.com/partdetail/...``) and records an evidence row with
``supplier_id: "jlcpcb"`` and ``assembly_class``; this module serves and assesses those rows.

Without evidence, the existing ``JLCPCBPCBACatalog.classify_part`` table is still reported, but
labelled ``heuristic`` with assembly stock unknown - never as a verified class.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from desk.component_intelligence.suppliers.capabilities import SupplierCapabilities
from desk.component_intelligence.suppliers.evidence import (
    EvidenceStore,
    EvidenceSupplierProvider,
    format_timestamp,
)
from desk.component_intelligence.suppliers.models import SupplierOffer

from .pcba_catalog import JLCPCBPCBACatalog

JLCPCB_SUPPLIER_ID = "jlcpcb"
JLCPCB_PARTS_NAME = "JLCPCB Parts Library"
JLCPCB_DOMAINS = ("jlcpcb.com",)
EXTENDED_FEE_USD_ESTIMATE = 3.00  # same estimate JLCPCBPCBACatalog.classify_part uses for Extended


class JlcpcbPartsProvider(EvidenceSupplierProvider):
    """JLCPCB parts library adapter: evidence-backed, no network access, never orders."""

    def __init__(self, store: Optional[EvidenceStore] = None,
                 capabilities: Optional[SupplierCapabilities] = None) -> None:
        store = store if store is not None else EvidenceStore()
        store.suppliers.setdefault(JLCPCB_SUPPLIER_ID, (JLCPCB_PARTS_NAME, JLCPCB_DOMAINS))
        super().__init__(JLCPCB_SUPPLIER_ID, JLCPCB_PARTS_NAME, store, capabilities)


@dataclass
class AssemblyAssessment:
    """Can JLCPCB assemble this part, in which class, and is that verified?"""
    lcsc_code: str
    assembly_class: str            # Basic / Preferred / Extended / UNKNOWN
    class_source: str              # "jlcpcb_evidence" | "heuristic" | "none"
    inventory: Optional[Dict[str, Any]] = None  # InventoryAssessment.to_dict() of the JLCPCB row
    source_url: str = ""
    verified_at: str = ""
    feeder_fee_usd_estimate: Optional[float] = None
    limitations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lcsc_code": self.lcsc_code,
            "assembly_class": self.assembly_class,
            "class_source": self.class_source,
            "inventory": self.inventory,
            "source_url": self.source_url,
            "verified_at": self.verified_at,
            "feeder_fee_usd_estimate": self.feeder_fee_usd_estimate,
            "limitations": list(self.limitations),
        }


def assess_assembly(
    lcsc_code: str,
    jlcpcb_offers: List[SupplierOffer],
    required_quantity: int = 1,
    package: str = "",
    now: Optional[float] = None,
    max_age_days: float = 7.0,
) -> AssemblyAssessment:
    """Assess JLCPCB assembly for one BOM line from JLCPCB evidence rows (pure)."""
    from desk.component_intelligence.procurement.inventory import classify_offer

    code = (lcsc_code or "").strip().upper()
    rows = sorted(jlcpcb_offers, key=lambda o: (-o.last_checked_ts, o.sku))
    if code:
        rows = [o for o in rows if o.sku.strip().upper() == code] or rows
    if rows:
        o = rows[0]
        inv = classify_offer(o, required_quantity, now=now, max_age_days=max_age_days)
        cls = o.assembly_class or "UNKNOWN"
        lims = list(inv.limitations)
        if not o.assembly_class:
            lims.append(f"JLCPCB {o.sku}: the parts library page did not show Basic/Preferred/Extended.")
        fee = {"Basic": 0.0, "Preferred": 0.0, "Extended": EXTENDED_FEE_USD_ESTIMATE}.get(cls)
        return AssemblyAssessment(
            lcsc_code=o.sku, assembly_class=cls, class_source="jlcpcb_evidence",
            inventory=inv.to_dict(), source_url=o.product_url,
            verified_at=format_timestamp(o.last_checked_ts) if o.last_checked_ts else "",
            feeder_fee_usd_estimate=fee, limitations=lims,
        )
    if code:
        info = JLCPCBPCBACatalog.classify_part(code, package)
        return AssemblyAssessment(
            lcsc_code=code, assembly_class=info.part_type, class_source="heuristic",
            feeder_fee_usd_estimate=info.feeder_fee_usd,
            limitations=[f"JLCPCB class for {code} is DESK's built-in heuristic, not read from the JLCPCB "
                         f"parts library; assembly stock is unknown. Verify at https://jlcpcb.com/parts."],
        )
    return AssemblyAssessment(
        lcsc_code="", assembly_class="UNKNOWN", class_source="none",
        limitations=["No LCSC/JLCPCB part number on this line; JLCPCB assembly cannot be assessed."],
    )
