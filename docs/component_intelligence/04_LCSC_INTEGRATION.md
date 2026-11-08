# LCSC Supplier Integration Specification

## 1. Scope & Implementation Status

LCSC Electronics (`https://www.lcsc.com/`) is integrated as the **initial commercial supplier provider** for DESK.

- **Status**: Implemented & unit-tested with realistic offline fixtures and API client adapters.
- **Live API Status**: Read-only catalog query contract implemented. Live API calls against official LCSC Open API (`https://wmsc.lcsc.com/`) require user-configured application credentials (`LCSC_CLIENT_ID` and `LCSC_CLIENT_SECRET`). In the absence of live credentials, the client operates in **deterministic offline fixture mode**.

---

## 2. Component Mapping Architecture

The `LcscDataMapper` translates LCSC structures into normalized DESK entities:
- **LCSC Product Code (`productCode`, e.g. `C11702`)** $\rightarrow$ `SupplierOffer.sku`.
- **LCSC Model (`productModel`, e.g. `0402WGF1001TCE`)** $\rightarrow$ `SupplierOffer.mpn` and `CanonicalComponent.mpn`.
- **LCSC Brand (`brandNameEn`, e.g. `Uni-Royal`)** $\rightarrow$ Normalized manufacturer.
- **Price Ladder (`productPriceList`)** $\rightarrow$ `List[PriceBreak]` with volume tier pricing in USD.
- **Stock (`stockNumber`)** $\rightarrow$ Real-time inventory count.
- **Datasheet URL (`pdfUrl`)** $\rightarrow$ Authoritative PDF reference.

---

## 3. Reliability & Security Controls

1. **Timeout & Retries**: Connection timeout: $5.0\,\text{s}$; Read timeout: $10.0\,\text{s}$; 3 bounded retries with exponential backoff.
2. **Fatal Error Classification**: 401 Unauthorized, 403 Forbidden, and 404 Not Found are treated as non-retryable fatal client errors.
3. **Secret Redaction**: API keys and secrets are loaded from environment variables and never exposed in debug logs or test fixtures.
