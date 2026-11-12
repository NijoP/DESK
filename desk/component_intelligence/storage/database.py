"""
Unified SQLite Component Database & Schema Migration Engine.
Pure Python standard library implementation with versioned migrations,
foreign key constraints, and transactional persistence.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = 1

MIGRATION_V1 = """
-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at REAL NOT NULL
);

-- Manufacturers table
CREATE TABLE IF NOT EXISTS manufacturers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    aliases_json TEXT NOT NULL DEFAULT '[]',
    homepage_url TEXT,
    created_at REAL NOT NULL
);

-- Canonical components table
CREATE TABLE IF NOT EXISTS components (
    desk_id TEXT PRIMARY KEY,
    manufacturer_name TEXT NOT NULL,
    normalized_manufacturer TEXT NOT NULL,
    mpn TEXT NOT NULL,
    normalized_mpn TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT,
    package TEXT,
    lifecycle_status TEXT NOT NULL DEFAULT 'UNKNOWN',
    verification_status TEXT NOT NULL DEFAULT 'UNVERIFIED',
    provenance TEXT NOT NULL DEFAULT 'local',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    attributes_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_components_norm_mfr_mpn ON components(normalized_manufacturer, normalized_mpn);
CREATE INDEX IF NOT EXISTS idx_components_mpn ON components(mpn);
CREATE INDEX IF NOT EXISTS idx_components_category ON components(category);

-- Datasheet sources table
CREATE TABLE IF NOT EXISTS datasheet_sources (
    id TEXT PRIMARY KEY,
    desk_id TEXT NOT NULL REFERENCES components(desk_id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    title TEXT,
    revision TEXT,
    sha256 TEXT,
    local_path TEXT,
    last_checked_ts REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_datasheets_desk_id ON datasheet_sources(desk_id);

-- Component specifications (typed electrical and physical parameters)
CREATE TABLE IF NOT EXISTS component_specifications (
    id TEXT PRIMARY KEY,
    desk_id TEXT NOT NULL REFERENCES components(desk_id) ON DELETE CASCADE,
    property_name TEXT NOT NULL,
    normalized_value REAL,
    unit TEXT,
    original_value TEXT NOT NULL,
    source_ref TEXT,
    extraction_method TEXT NOT NULL,
    verification_state TEXT NOT NULL DEFAULT 'UNVERIFIED',
    timestamp REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_specs_desk_prop ON component_specifications(desk_id, property_name);

-- Supplier offers table (commercial catalog entries)
CREATE TABLE IF NOT EXISTS supplier_offers (
    offer_id TEXT PRIMARY KEY,
    supplier_id TEXT NOT NULL,
    sku TEXT NOT NULL,
    canonical_desk_id TEXT NOT NULL REFERENCES components(desk_id) ON DELETE CASCADE,
    manufacturer_name TEXT NOT NULL,
    mpn TEXT NOT NULL,
    product_url TEXT,
    datasheet_url TEXT,
    description TEXT,
    package TEXT,
    stock INTEGER NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'USD',
    unit_price REAL NOT NULL DEFAULT 0.0,
    moq INTEGER NOT NULL DEFAULT 1,
    lead_time_days INTEGER,
    last_checked_ts REAL NOT NULL,
    raw_payload_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_supplier_offers_sku ON supplier_offers(sku);
CREATE INDEX IF NOT EXISTS idx_supplier_offers_desk_id ON supplier_offers(canonical_desk_id);
CREATE INDEX IF NOT EXISTS idx_supplier_offers_supplier_sku ON supplier_offers(supplier_id, sku);

-- Supplier pricing break tiers
CREATE TABLE IF NOT EXISTS supplier_price_breaks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    offer_id TEXT NOT NULL REFERENCES supplier_offers(offer_id) ON DELETE CASCADE,
    quantity INTEGER NOT NULL,
    unit_price REAL NOT NULL,
    currency TEXT NOT NULL DEFAULT 'USD'
);

CREATE INDEX IF NOT EXISTS idx_price_breaks_offer ON supplier_price_breaks(offer_id);

-- EDA library assets (symbols, footprints, 3D models)
CREATE TABLE IF NOT EXISTS eda_assets (
    asset_id TEXT PRIMARY KEY,
    canonical_desk_id TEXT NOT NULL REFERENCES components(desk_id) ON DELETE CASCADE,
    provider_id TEXT NOT NULL,
    asset_type TEXT NOT NULL, -- 'SYMBOL', 'FOOTPRINT', 'DEVICE', '3D_MODEL'
    asset_name TEXT NOT NULL,
    pin_count INTEGER NOT NULL DEFAULT 0,
    content_hash TEXT,
    raw_data_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_eda_assets_desk_id ON eda_assets(canonical_desk_id);
CREATE INDEX IF NOT EXISTS idx_eda_assets_provider_type ON eda_assets(provider_id, asset_type);

-- Verification records (V1-V4 audit log)
CREATE TABLE IF NOT EXISTS verification_records (
    id TEXT PRIMARY KEY,
    desk_id TEXT NOT NULL REFERENCES components(desk_id) ON DELETE CASCADE,
    level TEXT NOT NULL, -- 'V1_IDENTITY', 'V2_ELECTRICAL', 'V3_PHYSICAL', 'V4_PROCUREMENT'
    status TEXT NOT NULL, -- 'PASS', 'FAIL', 'UNKNOWN', 'NOT_RUN', 'STALE'
    evidence_json TEXT NOT NULL DEFAULT '{}',
    timestamp REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_verif_desk_level ON verification_records(desk_id, level);

-- Component relationships (alternatives, pin-compatible replacements)
CREATE TABLE IF NOT EXISTS component_relationships (
    id TEXT PRIMARY KEY,
    source_desk_id TEXT NOT NULL REFERENCES components(desk_id) ON DELETE CASCADE,
    target_desk_id TEXT NOT NULL REFERENCES components(desk_id) ON DELETE CASCADE,
    relationship_type TEXT NOT NULL, -- 'EXACT', 'EQUIVALENT', 'PACKAGE_COMPATIBLE', 'ELECTRICAL_COMPATIBLE', 'INCOMPATIBLE'
    compatibility_score REAL NOT NULL DEFAULT 1.0,
    notes TEXT,
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_comp_rel_source ON component_relationships(source_desk_id);
"""


class DatabaseManager:
    """Manages SQLite database connections and versioned migrations."""

    def __init__(self, db_path: Optional[str | Path] = None) -> None:
        if db_path is None:
            # Default to repo root / library / canonical.db
            repo_root = Path(__file__).resolve().parent.parent.parent.parent
            self.db_path = repo_root / "library" / "canonical.db"
        else:
            self.db_path = Path(db_path)

        os.makedirs(self.db_path.parent, exist_ok=True)
        self.initialize_schema()

    def get_connection(self) -> sqlite3.Connection:
        """Returns a connection configured with foreign keys and WAL mode."""
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.row_factory = sqlite3.Row
        return conn

    def initialize_schema(self) -> None:
        """Applies pending schema migrations."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version';")
            has_table = cursor.fetchone()

            current_version = 0
            if has_table:
                cursor.execute("SELECT MAX(version) FROM schema_version;")
                row = cursor.fetchone()
                if row and row[0] is not None:
                    current_version = row[0]

            if current_version < 1:
                cursor.executescript(MIGRATION_V1)
                # strftime instead of unixepoch(): the latter needs SQLite >= 3.38, which Python 3.9 builds do not bundle
                cursor.execute("INSERT INTO schema_version (version, applied_at) VALUES (1, CAST(strftime('%s', 'now') AS INTEGER));")
                conn.commit()
