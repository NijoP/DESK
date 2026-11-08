"""
LCSC Data Mapper.
Maps raw LCSC product structures into canonical DESK components and supplier offers.
"""

from __future__ import annotations

import time
from typing import List

from desk.component_intelligence.identity.models import CanonicalComponent
from desk.component_intelligence.identity.resolver import ComponentIdentityResolver
from desk.component_intelligence.suppliers.models import PriceBreak, SupplierOffer
from desk.component_intelligence.suppliers.providers.lcsc.models import LcscProductItem


class LcscDataMapper:
    """Translates LCSC payloads into normalized DESK entities."""

    @classmethod
    def to_canonical_component(cls, item: LcscProductItem) -> CanonicalComponent:
        """Derives a provisional canonical component from an LCSC product record."""
        category = f"{item.parentCatalogName} / {item.catalogName}".strip(" /")
        return ComponentIdentityResolver.resolve(
            manufacturer=item.brandNameEn,
            mpn=item.productModel,
            package=item.packageDetail,
            category=category,
            description=item.productDescEn,
            datasheet_url=item.pdfUrl,
            provenance="lcsc_supplier_catalog",
        )

    @classmethod
    def to_supplier_offer(cls, item: LcscProductItem) -> SupplierOffer:
        """Translates an LCSC product record into a normalized SupplierOffer."""
        norm_mfr = ComponentIdentityResolver.normalize_manufacturer(item.brandNameEn)
        norm_mpn = ComponentIdentityResolver.normalize_mpn(item.productModel)
        desk_id = ComponentIdentityResolver.generate_desk_id(norm_mfr, norm_mpn)

        # Convert price breaks
        price_breaks: List[PriceBreak] = []
        base_unit_price = 0.0
        for tier in item.productPriceList:
            price_breaks.append(
                PriceBreak(
                    quantity=tier.ladder,
                    unit_price=tier.productPrice,
                    currency=tier.currency,
                )
            )
        if price_breaks:
            # Sort ascending by quantity
            price_breaks.sort(key=lambda p: p.quantity)
            base_unit_price = price_breaks[0].unit_price

        product_url = f"https://www.lcsc.com/product-detail/{item.productCode}.html"

        return SupplierOffer(
            supplier_id="lcsc",
            supplier_name="LCSC Electronics",
            sku=item.productCode,
            canonical_desk_id=desk_id,
            manufacturer_name=item.brandNameEn,
            mpn=item.productModel,
            product_url=product_url,
            datasheet_url=item.pdfUrl,
            description=item.productDescEn,
            package=item.packageDetail,
            stock=item.stockNumber,
            currency="USD",
            unit_price=base_unit_price,
            price_breaks=price_breaks,
            moq=item.minPacketNumber,
            last_checked_ts=time.time(),
            raw_payload={
                "productCode": item.productCode,
                "productModel": item.productModel,
                "brandNameEn": item.brandNameEn,
                "catalogName": item.catalogName,
                "packageDetail": item.packageDetail,
                "stockNumber": item.stockNumber,
            },
        )
