"""Robu.in Supplier Provider (roadmap I-5).

Robu (https://robu.in/) publishes no parts API, and DESK holds no Robu account. As probed on
2026-11-21:

- ``robots.txt`` disallows ``/api/`` for every crawler except the ``/api/proxy/graphql`` route the
  site's own pages use, and allows public product pages;
- plain HTTP clients receive a Cloudflare "Just a moment..." browser challenge (HTTP 403), even for
  ``/sitemap.xml``.

DESK does not try to get around that challenge. Robu availability therefore enters only as
browser-agent evidence: an agent opens the public product page, records MPN, package, the stock
and price exactly as shown, the page URL and the time, and the record is validated by
``suppliers.evidence`` like any other offer. A Robu offer with no evidence simply does not exist;
it is never assumed to be in stock.
"""

from __future__ import annotations

from typing import Optional

from desk.component_intelligence.suppliers.capabilities import SupplierCapabilities
from desk.component_intelligence.suppliers.evidence import EvidenceStore, EvidenceSupplierProvider

ROBU_SUPPLIER_ID = "robu"
ROBU_NAME = "Robu.in"
ROBU_DOMAINS = ("robu.in",)


class RobuSupplierProvider(EvidenceSupplierProvider):
    """Robu.in adapter: evidence-backed, no network access."""

    def __init__(self, store: Optional[EvidenceStore] = None,
                 capabilities: Optional[SupplierCapabilities] = None) -> None:
        store = store if store is not None else EvidenceStore()
        store.suppliers.setdefault(ROBU_SUPPLIER_ID, (ROBU_NAME, ROBU_DOMAINS))
        super().__init__(ROBU_SUPPLIER_ID, ROBU_NAME, store, capabilities)
