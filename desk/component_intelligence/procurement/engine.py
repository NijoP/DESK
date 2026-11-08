"""
Procurement and Multi-Supplier BOM Optimization Engine.
Aggregates commercial distributor offers, evaluates volume price breaks,
identifies inventory shortages, and generates procurement readiness reports.
"""

from __future__ import annotations

import csv
import io
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from desk.component_intelligence.suppliers.models import SupplierOffer
from desk.component_intelligence.suppliers.registry import SupplierRegistry


@dataclass
class ProcurementLineItem:
    """Individual line item in an optimized procurement BOM."""
    designators: List[str]
    required_quantity: int
    mpn: str
    manufacturer: str
    package: str
    selected_supplier: str
    selected_sku: str
    available_stock: int
    unit_price: float
    extended_price: float
    currency: str = "USD"
    in_stock: bool = True
    verification_state: str = "PROVISIONAL"
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "designators": " ".join(sorted(self.designators)),
            "quantity": self.required_quantity,
            "mpn": self.mpn,
            "manufacturer": self.manufacturer,
            "package": self.package,
            "supplier": self.selected_supplier,
            "sku": self.selected_sku,
            "stock": self.available_stock,
            "unit_price": round(self.unit_price, 4),
            "extended_price": round(self.extended_price, 2),
            "currency": self.currency,
            "in_stock": self.in_stock,
            "warnings": "; ".join(self.warnings),
        }


@dataclass
class ProcurementBOMReport:
    """Complete multi-supplier procurement audit report."""
    batch_quantity: int
    total_extended_cost: float
    currency: str = "USD"
    total_unique_lines: int = 0
    total_components_placed: int = 0
    shortage_count: int = 0
    line_items: List[ProcurementLineItem] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def export_csv(self, file_path: str) -> None:
        """Exports the procurement BOM into standard CSV format."""
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Qty", "Designators", "MPN", "Manufacturer", "Package",
                "Supplier", "Supplier SKU", "Stock", "Unit Price", "Extended Cost", "Currency", "Status", "Warnings"
            ])
            for line in self.line_items:
                writer.writerow([
                    line.required_quantity,
                    " ".join(sorted(line.designators)),
                    line.mpn,
                    line.manufacturer,
                    line.package,
                    line.selected_supplier,
                    line.selected_sku,
                    line.available_stock,
                    f"{line.unit_price:.4f}",
                    f"{line.extended_price:.2f}",
                    line.currency,
                    "IN STOCK" if line.in_stock else "SHORTAGE",
                    "; ".join(line.warnings),
                ])


class ProcurementEngine:
    """Optimizes BOM component sourcing across registered suppliers."""

    @classmethod
    def build_procurement_bom(
        cls,
        parts: List[Dict[str, Any]],
        supplier_registry: SupplierRegistry,
        batch_quantity: int = 1,
    ) -> ProcurementBOMReport:
        # 1. Group parts by MPN
        grouped: Dict[str, Dict[str, Any]] = {}
        for p in parts:
            mpn = p.get("mpn", "").strip()
            if not mpn:
                continue
            if mpn not in grouped:
                grouped[mpn] = {
                    "mpn": mpn,
                    "manufacturer": p.get("manufacturer", "Generic"),
                    "package": p.get("package", ""),
                    "refs": [],
                    "lcsc_hint": p.get("lcsc", ""),
                }
            grouped[mpn]["refs"].append(p.get("ref", ""))

        total_cost = 0.0
        total_placed = 0
        shortages = 0
        line_items: List[ProcurementLineItem] = []
        global_warnings: List[str] = []

        # 2. Match each line item against supplier offers
        for mpn, info in sorted(grouped.items(), key=lambda kv: kv[0]):
            qty_per_board = len(info["refs"])
            total_required = qty_per_board * batch_quantity
            total_placed += total_required

            # Query offers across all enabled suppliers
            offers = supplier_registry.get_offers_for_mpn(mpn)
            # If explicit LCSC SKU hint was present, query by SKU if no MPN offers found
            if not offers and info["lcsc_hint"]:
                lcsc_p = supplier_registry.get_provider("lcsc")
                if lcsc_p:
                    single_offer = lcsc_p.get_component(info["lcsc_hint"])
                    if single_offer:
                        offers = [single_offer]

            line_warnings: List[str] = []
            if not offers:
                shortages += 1
                line_warnings.append(f"No supplier offer found for MPN '{mpn}'")
                line_items.append(
                    ProcurementLineItem(
                        designators=info["refs"],
                        required_quantity=total_required,
                        mpn=mpn,
                        manufacturer=info["manufacturer"],
                        package=info["package"],
                        selected_supplier="NONE",
                        selected_sku="N/A",
                        available_stock=0,
                        unit_price=0.0,
                        extended_price=0.0,
                        in_stock=False,
                        warnings=line_warnings,
                    )
                )
                continue

            # Optimize price and stock availability
            in_stock_offers = [o for o in offers if o.stock >= total_required]
            candidate_pool = in_stock_offers if in_stock_offers else offers

            # Pick lowest unit price for required volume
            best_offer = min(candidate_pool, key=lambda o: o.get_price_for_quantity(total_required))
            unit_price = best_offer.get_price_for_quantity(total_required)
            extended = unit_price * total_required
            total_cost += extended

            is_in_stock = best_offer.stock >= total_required
            if not is_in_stock:
                shortages += 1
                line_warnings.append(
                    f"Stock shortage at {best_offer.supplier_name}: available {best_offer.stock}, need {total_required}"
                )

            line_items.append(
                ProcurementLineItem(
                    designators=info["refs"],
                    required_quantity=total_required,
                    mpn=mpn,
                    manufacturer=best_offer.manufacturer_name or info["manufacturer"],
                    package=best_offer.package or info["package"],
                    selected_supplier=best_offer.supplier_name,
                    selected_sku=best_offer.sku,
                    available_stock=best_offer.stock,
                    unit_price=unit_price,
                    extended_price=extended,
                    currency=best_offer.currency,
                    in_stock=is_in_stock,
                    warnings=line_warnings,
                )
            )

        if shortages > 0:
            global_warnings.append(f"{shortages} BOM line items have inventory shortages or missing offers.")

        return ProcurementBOMReport(
            batch_quantity=batch_quantity,
            total_extended_cost=round(total_cost, 2),
            currency="USD",
            total_unique_lines=len(line_items),
            total_components_placed=total_placed,
            shortage_count=shortages,
            line_items=line_items,
            warnings=global_warnings,
        )
