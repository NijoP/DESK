"""
High-Level Component Intelligence Repository.
Provides clean Python transactional access to the normalized SQLite store.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from desk.component_intelligence.identity.models import (
    CanonicalComponent,
    DatasheetReference,
    IdentityVerificationStatus,
    LifecycleStatus,
)
from desk.component_intelligence.storage.database import DatabaseManager
from desk.component_intelligence.suppliers.models import PriceBreak, SupplierOffer


class ComponentRepository:
    """Repository handling CRUD operations for components, offers, specs, and assets."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None) -> None:
        self.db = db_manager or DatabaseManager()

    def upsert_component(self, comp: CanonicalComponent) -> str:
        """Inserts or updates a canonical component record."""
        now = time.time()
        with self.db.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO components (
                    desk_id, manufacturer_name, normalized_manufacturer,
                    mpn, normalized_mpn, category, description, package,
                    lifecycle_status, verification_status, provenance,
                    created_at, updated_at, attributes_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(desk_id) DO UPDATE SET
                    manufacturer_name = excluded.manufacturer_name,
                    normalized_manufacturer = excluded.normalized_manufacturer,
                    mpn = excluded.mpn,
                    normalized_mpn = excluded.normalized_mpn,
                    category = excluded.category,
                    description = excluded.description,
                    package = excluded.package,
                    lifecycle_status = excluded.lifecycle_status,
                    verification_status = excluded.verification_status,
                    updated_at = excluded.updated_at,
                    attributes_json = excluded.attributes_json
                """,
                (
                    comp.desk_id,
                    comp.manufacturer_name,
                    comp.normalized_manufacturer,
                    comp.mpn,
                    comp.normalized_mpn,
                    comp.category,
                    comp.description,
                    comp.package,
                    comp.lifecycle_status.value,
                    comp.verification_status.value,
                    comp.provenance,
                    comp.created_at,
                    now,
                    json.dumps(comp.attributes),
                ),
            )

            # Insert datasheets
            for ds in comp.datasheets:
                conn.execute(
                    """
                    INSERT INTO datasheet_sources (
                        id, desk_id, url, title, revision, sha256, local_path, last_checked_ts
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        url = excluded.url,
                        last_checked_ts = excluded.last_checked_ts
                    """,
                    (
                        ds.id,
                        comp.desk_id,
                        ds.url,
                        ds.title,
                        ds.revision,
                        ds.sha256,
                        ds.local_path,
                        ds.last_checked_ts,
                    ),
                )
            conn.commit()
        return comp.desk_id

    def get_component(self, desk_id: str) -> Optional[CanonicalComponent]:
        """Retrieves a component by its internal DESK ID."""
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT * FROM components WHERE desk_id = ?", (desk_id,)).fetchone()
            if not row:
                return None
            return self._row_to_component(conn, row)

    def find_by_mpn(self, mpn: str) -> List[CanonicalComponent]:
        """Finds components matching an exact or normalized MPN."""
        clean_mpn = mpn.strip().upper()
        with self.db.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM components WHERE normalized_mpn = ? OR mpn = ?",
                (clean_mpn, mpn.strip()),
            ).fetchall()
            return [self._row_to_component(conn, r) for r in rows]

    def search(self, query: str, limit: int = 50) -> List[CanonicalComponent]:
        """Performs multi-criteria substring search across MPN, manufacturer, and description."""
        pattern = f"%{query.strip()}%"
        with self.db.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM components
                WHERE mpn LIKE ? OR normalized_mpn LIKE ? OR manufacturer_name LIKE ? OR description LIKE ?
                ORDER BY mpn ASC LIMIT ?
                """,
                (pattern, pattern, pattern, pattern, limit),
            ).fetchall()
            return [self._row_to_component(conn, r) for r in rows]

    def upsert_supplier_offer(self, offer: SupplierOffer) -> None:
        """Inserts or updates a supplier commercial offer and its pricing breaks."""
        offer_id = f"{offer.supplier_id}_{offer.sku}"
        with self.db.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO supplier_offers (
                    offer_id, supplier_id, sku, canonical_desk_id, manufacturer_name,
                    mpn, product_url, datasheet_url, description, package, stock,
                    currency, unit_price, moq, lead_time_days, last_checked_ts, raw_payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(offer_id) DO UPDATE SET
                    stock = excluded.stock,
                    unit_price = excluded.unit_price,
                    currency = excluded.currency,
                    last_checked_ts = excluded.last_checked_ts,
                    raw_payload_json = excluded.raw_payload_json
                """,
                (
                    offer_id,
                    offer.supplier_id,
                    offer.sku,
                    offer.canonical_desk_id,
                    offer.manufacturer_name,
                    offer.mpn,
                    offer.product_url,
                    offer.datasheet_url,
                    offer.description,
                    offer.package,
                    offer.stock,
                    offer.currency,
                    offer.unit_price,
                    offer.moq,
                    offer.lead_time_days,
                    offer.last_checked_ts,
                    json.dumps(offer.raw_payload),
                ),
            )

            # Refresh price breaks
            conn.execute("DELETE FROM supplier_price_breaks WHERE offer_id = ?", (offer_id,))
            for pb in offer.price_breaks:
                conn.execute(
                    """
                    INSERT INTO supplier_price_breaks (offer_id, quantity, unit_price, currency)
                    VALUES (?, ?, ?, ?)
                    """,
                    (offer_id, pb.quantity, pb.unit_price, pb.currency),
                )
            conn.commit()

    def get_offers_for_component(self, desk_id: str) -> List[SupplierOffer]:
        """Retrieves all commercial offers available for a canonical component."""
        offers: List[SupplierOffer] = []
        with self.db.get_connection() as conn:
            rows = conn.execute("SELECT * FROM supplier_offers WHERE canonical_desk_id = ?", (desk_id,)).fetchall()
            for r in rows:
                offer_id = r["offer_id"]
                pb_rows = conn.execute(
                    "SELECT * FROM supplier_price_breaks WHERE offer_id = ? ORDER BY quantity ASC",
                    (offer_id,),
                ).fetchall()
                pbs = [PriceBreak(quantity=p["quantity"], unit_price=p["unit_price"], currency=p["currency"]) for p in pb_rows]

                offers.append(
                    SupplierOffer(
                        supplier_id=r["supplier_id"],
                        supplier_name=r["supplier_id"].upper(),
                        sku=r["sku"],
                        canonical_desk_id=r["canonical_desk_id"],
                        manufacturer_name=r["manufacturer_name"],
                        mpn=r["mpn"],
                        product_url=r["product_url"],
                        datasheet_url=r["datasheet_url"],
                        description=r["description"],
                        package=r["package"],
                        stock=r["stock"],
                        currency=r["currency"],
                        unit_price=r["unit_price"],
                        price_breaks=pbs,
                        moq=r["moq"],
                        lead_time_days=r["lead_time_days"],
                        last_checked_ts=r["last_checked_ts"],
                    )
                )
        return offers

    def _row_to_component(self, conn: Any, row: Any) -> CanonicalComponent:
        ds_rows = conn.execute(
            "SELECT * FROM datasheet_sources WHERE desk_id = ?",
            (row["desk_id"],),
        ).fetchall()
        datasheets = [
            DatasheetReference(
                id=d["id"],
                url=d["url"],
                title=d["title"] or "",
                revision=d["revision"],
                sha256=d["sha256"],
                local_path=d["local_path"],
                last_checked_ts=d["last_checked_ts"],
            )
            for d in ds_rows
        ]

        return CanonicalComponent(
            desk_id=row["desk_id"],
            manufacturer_name=row["manufacturer_name"],
            normalized_manufacturer=row["normalized_manufacturer"],
            mpn=row["mpn"],
            normalized_mpn=row["normalized_mpn"],
            category=row["category"],
            description=row["description"] or "",
            package=row["package"] or "",
            datasheets=datasheets,
            lifecycle_status=LifecycleStatus(row["lifecycle_status"]),
            verification_status=IdentityVerificationStatus(row["verification_status"]),
            provenance=row["provenance"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            attributes=json.loads(row["attributes_json"]) if row["attributes_json"] else {},
        )
