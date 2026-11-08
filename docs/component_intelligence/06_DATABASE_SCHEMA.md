# Unified SQLite Component Database Schema

## 1. Storage Overview

The local-first component store is backed by SQLite (`library/canonical.db`) utilizing Write-Ahead Logging (`WAL`) and strict foreign key integrity (`PRAGMA foreign_keys = ON;`).

---

## 2. Relational Schema & Entity-Relationship Map

```
  ┌──────────────────┐          1:N         ┌───────────────────────┐
  │   manufacturers  │ ───────────────────> │      components       │
  └──────────────────┘                      └───────────┬───────────┘
                                                        │
                      ┌─────────────────────────────────┼─────────────────────────────────┐
                      │ 1:N                             │ 1:N                             │ 1:N
                      ▼                                 ▼                                 ▼
         ┌─────────────────────────┐       ┌─────────────────────────┐       ┌─────────────────────────┐
         │    datasheet_sources    │       │ component_specifications│       │     supplier_offers     │
         └─────────────────────────┘       └─────────────────────────┘       └───────────┬─────────────┘
                                                                                         │ 1:N
                                                                                         ▼
                                                                            ┌─────────────────────────┐
                                                                            │  supplier_price_breaks  │
                                                                            └─────────────────────────┘
```

---

## 3. Core Tables

1. `components`: Canonical component identity, manufacturer, MPN, normalized keys, category, description, package, and lifecycle status.
2. `datasheet_sources`: Authoritative PDF datasheet URLs, sha256 hashes, and local cache paths.
3. `component_specifications`: Typed electrical (voltage, current, power, capacitance, resistance) and physical parameters.
4. `supplier_offers`: Distributor SKU, live stock count, base unit price, MOQ, and timestamped quote provenance.
5. `supplier_price_breaks`: Volume price ladders per supplier offer.
6. `eda_assets`: CAD symbol pins, footprint geometries, and content hashes.
7. `verification_records`: V1–V4 verification evidence history.
8. `component_relationships`: Cross-reference compatibility mappings.
