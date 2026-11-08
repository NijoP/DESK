"""
Typed LCSC Provider Commercial Data Models.
Represents raw structures returned by LCSC catalog and product APIs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class LcscPriceTier:
    """LCSC volume tier price point."""
    ladder: int
    productPrice: float
    currency: str = "USD"


@dataclass
class LcscProductItem:
    """Standard LCSC product catalog item representation."""
    productCode: str              # LCSC part number (e.g., "C11702")
    productModel: str             # MPN (e.g., "0402WGF1001TCE")
    brandNameEn: str              # Manufacturer (e.g., "Uni-Royal")
    catalogName: str = ""         # Sub-category
    parentCatalogName: str = ""   # Main category
    packageDetail: str = ""       # Package designation
    stockNumber: int = 0          # Inventory quantity
    productPriceList: List[LcscPriceTier] = field(default_factory=list)
    productUnit: str = "piece"
    minPacketNumber: int = 1      # MOQ
    pdfUrl: Optional[str] = None  # Datasheet link
    productDescEn: str = ""       # English description
    productWeight: float = 0.0
    isRoHS: bool = True

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LcscProductItem":
        tiers = []
        raw_prices = data.get("productPriceList") or data.get("prices") or []
        for p in raw_prices:
            ladder = int(p.get("ladder", p.get("qty", 1)))
            price = float(p.get("productPrice", p.get("price", 0.0)))
            curr = str(p.get("currency", "USD"))
            tiers.append(LcscPriceTier(ladder=ladder, productPrice=price, currency=curr))

        return cls(
            productCode=str(data.get("productCode", data.get("lcsc_id", ""))),
            productModel=str(data.get("productModel", data.get("mpn", ""))),
            brandNameEn=str(data.get("brandNameEn", data.get("manufacturer", "Generic"))),
            catalogName=str(data.get("catalogName", "")),
            parentCatalogName=str(data.get("parentCatalogName", "")),
            packageDetail=str(data.get("packageDetail", data.get("package", ""))),
            stockNumber=int(data.get("stockNumber", data.get("stock", 0))),
            productPriceList=tiers,
            productUnit=str(data.get("productUnit", "piece")),
            minPacketNumber=int(data.get("minPacketNumber", data.get("moq", 1))),
            pdfUrl=data.get("pdfUrl") or data.get("datasheet"),
            productDescEn=str(data.get("productDescEn", data.get("description", ""))),
            productWeight=float(data.get("productWeight", 0.0)),
            isRoHS=bool(data.get("isRoHS", True)),
        )
