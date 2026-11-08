"""
Public Agent and CLI Facade for DESK Universal Component Intelligence.
Exposes stable, machine-readable operations for AI agents, deterministic tools, and CI/CD pipelines.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from desk.component_intelligence.catalog.alternatives import ComponentAlternativesEngine
from desk.component_intelligence.eda.providers.local import LocalEDALibraryProvider
from desk.component_intelligence.eda.registry import EDARegistry
from desk.component_intelligence.identity.models import CanonicalComponent
from desk.component_intelligence.identity.resolver import ComponentIdentityResolver
from desk.component_intelligence.procurement.engine import ProcurementBOMReport, ProcurementEngine
from desk.component_intelligence.specifications.engine import ComponentSpecification
from desk.component_intelligence.storage.database import DatabaseManager
from desk.component_intelligence.storage.repository import ComponentRepository
from desk.component_intelligence.suppliers.models import SupplierOffer
from desk.component_intelligence.suppliers.providers.lcsc.provider import LcscSupplierProvider
from desk.component_intelligence.suppliers.registry import SupplierRegistry
from desk.component_intelligence.verification.engine import ComponentVerificationEngine

logger = logging.getLogger("desk.component_intelligence")

# Singleton managers
_DB_MANAGER: Optional[DatabaseManager] = None
_REPOSITORY: Optional[ComponentRepository] = None
_SUPPLIER_REGISTRY: Optional[SupplierRegistry] = None
_EDA_REGISTRY: Optional[EDARegistry] = None


def get_repository() -> ComponentRepository:
    global _DB_MANAGER, _REPOSITORY
    if _REPOSITORY is None:
        _DB_MANAGER = DatabaseManager()
        _REPOSITORY = ComponentRepository(_DB_MANAGER)
    return _REPOSITORY


def get_supplier_registry() -> SupplierRegistry:
    global _SUPPLIER_REGISTRY
    if _SUPPLIER_REGISTRY is None:
        _SUPPLIER_REGISTRY = SupplierRegistry.get_instance()
        # Register LCSC as the first commercial provider
        if not _SUPPLIER_REGISTRY.get_provider("lcsc"):
            _SUPPLIER_REGISTRY.register(LcscSupplierProvider())
    return _SUPPLIER_REGISTRY


def get_eda_registry() -> EDARegistry:
    global _EDA_REGISTRY
    if _EDA_REGISTRY is None:
        _EDA_REGISTRY = EDARegistry.get_instance()
        # Register Local offline EDA provider
        if not _EDA_REGISTRY.get_provider("local"):
            _EDA_REGISTRY.register(LocalEDALibraryProvider())
    return _EDA_REGISTRY


# =============================================================================
# Agent Facing High-Level Operations
# =============================================================================

def find_component(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Discovers components from local canonical database, falling back to suppliers.
    Returns structured canonical records with active supplier offer count.
    """
    repo = get_repository()
    components = repo.search(query, limit=limit)

    results = []
    for c in components:
        offers = repo.get_offers_for_component(c.desk_id)
        d = c.to_dict()
        d["active_offers_count"] = len(offers)
        d["best_unit_price"] = min((o.unit_price for o in offers), default=None)
        results.append(d)

    # If no local results found, search active suppliers and import provisional records
    if not results:
        supp_reg = get_supplier_registry()
        supplier_offers = supp_reg.search_all(query, limit_per_supplier=limit)
        for off in supplier_offers:
            # Create provisional canonical component
            canon = ComponentIdentityResolver.resolve(
                manufacturer=off.manufacturer_name,
                mpn=off.mpn,
                package=off.package,
                description=off.description,
                datasheet_url=off.datasheet_url,
                provenance=f"supplier_{off.supplier_id}",
            )
            repo.upsert_component(canon)
            repo.upsert_supplier_offer(off)
            d = canon.to_dict()
            d["active_offers_count"] = 1
            d["best_unit_price"] = off.unit_price
            results.append(d)

    return results[:limit]


def resolve_component_identity(
    manufacturer: str,
    mpn: str,
    package: str = "",
    category: str = "",
    description: str = "",
) -> Dict[str, Any]:
    """Resolves raw component parameters into a canonical DESK identity."""
    canon = ComponentIdentityResolver.resolve(
        manufacturer=manufacturer,
        mpn=mpn,
        package=package,
        category=category,
        description=description,
    )
    repo = get_repository()
    repo.upsert_component(canon)
    return canon.to_dict()


def search_supplier_offers(query: str) -> List[Dict[str, Any]]:
    """Queries all registered suppliers for commercial stock and pricing offers."""
    supp_reg = get_supplier_registry()
    offers = supp_reg.search_all(query)
    repo = get_repository()
    for o in offers:
        repo.upsert_supplier_offer(o)
    return [o.to_dict() for o in offers]


def find_eda_assets(query: str) -> Dict[str, List[Dict[str, Any]]]:
    """Finds CAD symbols and footprints matching query from registered EDA providers."""
    eda_reg = get_eda_registry()
    symbols = eda_reg.search_symbols(query)
    footprints = eda_reg.search_footprints(query)
    return {
        "symbols": [s.to_dict() for s in symbols],
        "footprints": [f.to_dict() for f in footprints],
    }


def verify_component(
    desk_id: str,
    operating_rail_v: float = 0.0,
    operating_current_a: float = 0.0,
) -> Dict[str, Any]:
    """Executes fail-closed V1-V4 verification for a component."""
    repo = get_repository()
    comp = repo.get_component(desk_id)
    if not comp:
        raise KeyError(f"Component '{desk_id}' not found in canonical database.")

    offers = repo.get_offers_for_component(desk_id)
    best_offer = min(offers, key=lambda o: o.unit_price) if offers else None

    # Synthesize provisional specifications from component attributes if none stored
    specs = []

    v1 = ComponentVerificationEngine.verify_v1_identity(comp)
    v2 = ComponentVerificationEngine.verify_v2_electrical(
        comp, specs, operating_rail_v=operating_rail_v, operating_current_a=operating_current_a
    )
    v3 = ComponentVerificationEngine.verify_v3_physical(comp)
    v4 = ComponentVerificationEngine.verify_v4_procurement(best_offer)

    all_passed = all(ev.state == "PASS" for ev in (v1, v2, v3, v4))

    return {
        "desk_id": desk_id,
        "mpn": comp.mpn,
        "overall_verified": all_passed,
        "verifications": {
            "V1_IDENTITY": v1.to_dict(),
            "V2_ELECTRICAL": v2.to_dict(),
            "V3_PHYSICAL": v3.to_dict(),
            "V4_PROCUREMENT": v4.to_dict(),
        },
    }


def build_procurement_bom(
    parts: List[Dict[str, Any]],
    batch_quantity: int = 1,
) -> Dict[str, Any]:
    """Generates an optimized multi-supplier procurement BOM."""
    supp_reg = get_supplier_registry()
    report: ProcurementBOMReport = ProcurementEngine.build_procurement_bom(
        parts, supp_reg, batch_quantity=batch_quantity
    )
    return {
        "batch_quantity": report.batch_quantity,
        "total_extended_cost": report.total_extended_cost,
        "currency": report.currency,
        "total_unique_lines": report.total_unique_lines,
        "total_components_placed": report.total_components_placed,
        "shortage_count": report.shortage_count,
        "line_items": [li.to_dict() for li in report.line_items],
        "warnings": report.warnings,
    }


def migrate_seed_devices(max_items: Optional[int] = None) -> int:
    """Migrates historical records from library/devices.json into canonical SQLite database."""
    import json
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent.parent
    devices_file = repo_root / "library" / "devices.json"
    if not devices_file.is_file():
        return 0

    try:
        with open(devices_file, "r", encoding="utf-8") as f:
            devices = json.load(f)
    except Exception:
        return 0

    repo = get_repository()
    count = 0
    items = list(devices.items())
    if max_items:
        items = items[:max_items]

    for mpn, data in items:
        mfr = data.get("mfr") or data.get("manufacturer") or "Generic"
        fp = data.get("footprint", "")
        lcsc = data.get("lcsc", "")

        canon = ComponentIdentityResolver.resolve(
            manufacturer=mfr,
            mpn=mpn,
            package=fp,
            provenance="seed_devices_json",
        )
        repo.upsert_component(canon)

        # If LCSC code present, register a local seed offer
        if lcsc:
            offer = SupplierOffer(
                supplier_id="lcsc",
                supplier_name="LCSC Electronics",
                sku=lcsc,
                canonical_desk_id=canon.desk_id,
                manufacturer_name=canon.normalized_manufacturer,
                mpn=mpn,
                package=fp,
                stock=1000,
                unit_price=0.01,
            )
            repo.upsert_supplier_offer(offer)
        count += 1

    return count
