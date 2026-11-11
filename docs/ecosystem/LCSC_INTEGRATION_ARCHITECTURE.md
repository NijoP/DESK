# LCSC Integration Architecture

**Inventory date:** 2026-11-12 (read-only audit of `desk/component_intelligence`). **Owner:** LCSC Component Intelligence Team, reporting to the Product Manager. **Rule:** never invent an LCSC C-number; every live value carries its source and retrieval timestamp; when live data is unavailable the record is marked CACHED, STALE, ESTIMATED or UNVERIFIED.

## What exists today (facts)

| Piece | File | State |
|---|---|---|
| Supplier abstraction | `suppliers/base.py` (`SupplierProvider`: search, get_component, get_offers, availability, pricing), `suppliers/registry.py` (`SupplierRegistry.search_all`, `get_offers_for_mpn`) | EXISTS, offline-tested |
| Offer model | `suppliers/models.py` `SupplierOffer` (sku, mpn, manufacturer, product_url, datasheet_url, package, stock, currency, unit_price, price_breaks, moq, lead_time_days, `last_checked_ts`, raw_payload) | EXISTS |
| LCSC client | `suppliers/providers/lcsc/client.py`: base URL `https://wmsc.lcsc.com/ftps/wm/product`, `POST /search`, `GET /detail?productCode=`, headers `X-Client-Id`/`X-Client-Secret` from `LCSC_CLIENT_ID`/`LCSC_CLIENT_SECRET`, 3 retries with backoff | code present; **endpoint never confirmed live**; without credentials it serves 5 fixture parts |
| Mapper | `lcsc/mapper.py` → `CanonicalComponent` + `SupplierOffer` from `productPriceList`, `stockNumber`, `pdfUrl`, `minPacketNumber`; currency hard-coded USD | EXISTS |
| Canonical identity | `identity/resolver.py` (manufacturer alias normalisation, deterministic `desk_id`), `identity/models.py` (`CanonicalComponent`, `DatasheetReference` with sha256/local_path never filled, `LifecycleStatus` never filled) | PARTIAL |
| Storage | `storage/database.py` SQLite `library/canonical.db` (components, datasheet_sources, component_specifications, supplier_offers, price_breaks, eda_assets, verification_records, relationships); `storage/repository.py` covers only components and offers | PARTIAL |
| Real C-number source | `tools/resolve.py`: EasyEDA library search `eda.lib_Device.search(q)` through the gateway, takes `supplierId`; exact match on name/lcsc/mfr else human `--pick`; cached in `library/devices.json` (111 entries, 16 with an LCSC id) | EXISTS (live use evidenced by real uuids; no recorded verification) |
| Specs | `specifications/engine.py` parsers (capacitance, resistance, voltage, current, power); nothing extracts from datasheets; specs are never stored | PARTIAL |
| Verification | `verification/engine.py` V1 identity, V2 electrical (1.5× capacitor derating; UNKNOWN without specs), V3 physical (package, pin count if pins supplied), V4 procurement (stock, 7-day staleness) | PARTIAL; `api.verify_component` always passes empty specs |
| Alternatives | `catalog/alternatives.py` evaluates a *given* candidate (package, pins, V/I) | PARTIAL; no candidate search |
| Mouser | `providers/mouser/provider.py` offline catalogue of 2 parts; no HTTP | fixture only |

## Target architecture (ADAPT existing modules; no second implementation)

```
requirements/block spec ──> ComponentSelector (new, catalog/selector.py)
        │                      │ queries
        │                      ▼
        │            SupplierRegistry ──> LcscSupplierProvider (official API when credentials exist;
        │                                  otherwise EasyEDA library search via tools/resolve.py;
        │                                  otherwise CACHED record from canonical.db, flagged)
        │                      │
        ▼                      ▼
   SelectionMatrix (F1-F7) <── specs (datasheet-extracted | supplier catalogue | assumed, each flagged)
        │
        ▼
   CanonicalComponent + DatasheetReference(sha256, local_path) + SupplierOffer(last_checked_ts, source)
        │
        ▼
   library/canonical.db (versioned records) ──> BOM lines (see BOM_CPL_VALIDATION_SPECIFICATION.md)
```

Record contract for every selected component: manufacturer, MPN, LCSC C-number (or UNKNOWN), datasheet reference (URL + sha256 when downloaded), electrical ratings with extraction method, package, footprint, pin map provenance, procurement (stock, price, MOQ, lead time, timestamp, source), selection justification (matrix row), verification status (V1-V4).

## Data access policy

1. Official LCSC API with user-provided credentials (existing client) — status UNVERIFIED until a live call succeeds; the first live call must be logged with its response shape.
2. EasyEDA Pro library search through the gateway (existing `resolve.py`) — the only live source of C-numbers today.
3. Documented catalogue exports (CSV) placed by the user — to be supported by the same mapper.
4. User-authorised browser workflow — out of scope for automation.
No undocumented endpoints, no scraping, no bypass of rate limits. Every live result stores `source` and `retrieved_at`; a record older than 7 days is STALE (existing V4 rule).

## Work packages

| ID | Package | Owner | Cx |
|---|---|---|---|
| LC-01 | Live-verify the LCSC client against the documented API once credentials exist; record the response schema; add `source`/`retrieved_at` to offers and quotes | LCSC | S |
| LC-02 | `ComponentSelector` + F1-F7 selection matrix (electrical fit, pin fit, thermal, package, availability, price, lifecycle) with justification text; price never outranks fit | LCSC + HW | M |
| LC-03 | Datasheet retrieval: download `pdfUrl`, store sha256 and local path, link to `DatasheetReference` | LCSC | S |
| LC-04 | Spec extraction pipeline: supplier catalogue attributes first (DATASHEET_EXTRACTED only when a human or verified parser confirms), stored in `component_specifications`, used by V2 | LCSC + AI | M |
| LC-05 | Alternatives search: query suppliers by package + key specs, rank with `ComponentAlternativesEngine` | LCSC | M |
| LC-06 | Lifecycle/availability from supplier fields; `LifecycleStatus` populated | LCSC | S |
| LC-07 | Repository methods for specs, eda_assets, verification_records; per-record version history | SW | M |
| LC-08 | Per-component MPN/LCSC readback from EasyEDA (documented property getter; the generic read returned nothing in the live observation) | PCB | S |
