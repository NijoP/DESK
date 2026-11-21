"""Supplier evidence ingestion (roadmap I-5).

DESK has no supplier credentials, and some suppliers cannot be read by a program at all (Robu sits
behind a Cloudflare browser challenge; JLCPCB's robots.txt disallows ``/api``). For those, a
browser-capable agent reads the public product page and writes what it saw into an evidence file.
This module validates each record and turns it into an ordinary ``SupplierOffer`` with
``availability_source = agent_evidence``, so it goes through exactly the same inventory classifier,
ranking and report as offers DESK fetched itself.

Evidence file (JSON, UTF-8)::

    {"schema": "desk.sourcing.evidence/1",
     "records": [{
        "supplier_id": "robu",                      # required, must be a known supplier
        "mpn": "AMS1117-3.3",                       # required
        "manufacturer": "AMS",
        "sku": "...",                               # supplier part number (defaults to the MPN)
        "package": "SOT-223", "footprint": "...",
        "source_url": "https://robu.in/product/...",  # required, https, on the supplier's own domain
        "verified_at": "2026-11-21T10:00:00Z",      # required, ISO 8601 with a timezone
        "stock": 120,                               # integer >= 0, or null when the page shows none
        "stock_text": "120 in stock",               # the words as shown, kept for audit
        "backorder": false, "lead_time_days": null,
        "lifecycle": "active",
        "price": 0.12, "currency": "USD",           # null price -> PRICE_UNAVAILABLE, never invented
        "price_breaks": [{"quantity": 10, "unit_price": 0.10}],
        "datasheet_url": "...", "description": "...",
        "specs": {"voltage_v": 15, "current_a": 1.0, "pin_count": 4},
        "alternative_for": "",                      # MPN this part is proposed to replace
        "assembly_class": "",                       # JLCPCB parts library: Basic / Preferred / Extended
        "collected_by": "browser-agent", "notes": ""}]}

A record that fails validation is rejected with its reasons; it never becomes an offer.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

from desk.component_intelligence.identity.resolver import ComponentIdentityResolver
from desk.component_intelligence.suppliers.base import SupplierProvider
from desk.component_intelligence.suppliers.capabilities import SupplierCapabilities
from desk.component_intelligence.suppliers.models import SOURCE_AGENT_EVIDENCE, PriceBreak, SupplierOffer

EVIDENCE_SCHEMA = "desk.sourcing.evidence/1"

# supplier_id -> (display name, domains a source_url may be on). A new supplier is added here (or
# passed to EvidenceStore) - the classifier, ranking and report do not change.
DEFAULT_SUPPLIERS: Dict[str, Tuple[str, Tuple[str, ...]]] = {
    "robu": ("Robu.in", ("robu.in",)),
    "lcsc": ("LCSC Electronics", ("lcsc.com",)),
    "jlcpcb": ("JLCPCB Parts Library", ("jlcpcb.com",)),
    "mouser": ("Mouser Electronics", ("mouser.com", "mouser.in")),
}

_CURRENCY = re.compile(r"^[A-Z]{3}$")
_ASSEMBLY_CLASSES = ("Basic", "Preferred", "Extended")


def parse_timestamp(text: Any) -> Optional[float]:
    """ISO 8601 with an explicit timezone -> epoch seconds. Naive or unparsable -> None."""
    if not isinstance(text, str) or not text.strip():
        return None
    t = text.strip()
    if t.endswith("Z") or t.endswith("z"):
        t = t[:-1] + "+00:00"
    try:
        d = _dt.datetime.fromisoformat(t)
    except ValueError:
        return None
    if d.tzinfo is None:
        return None
    return d.timestamp()


def format_timestamp(ts: float) -> str:
    return _dt.datetime.fromtimestamp(ts, tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _host_allowed(url: str, domains: Iterable[str]) -> bool:
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in domains)


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def validate_record(
    rec: Any,
    suppliers: Optional[Dict[str, Tuple[str, Tuple[str, ...]]]] = None,
    now: Optional[float] = None,
) -> List[str]:
    """Return the list of problems with one evidence record (empty = valid)."""
    suppliers = DEFAULT_SUPPLIERS if suppliers is None else suppliers
    if not isinstance(rec, dict):
        return ["record is not a JSON object"]
    errs: List[str] = []
    sid = rec.get("supplier_id")
    if not isinstance(sid, str) or sid not in suppliers:
        errs.append(f"supplier_id {sid!r} is not a known supplier ({', '.join(sorted(suppliers))})")
    if not isinstance(rec.get("mpn"), str) or not rec["mpn"].strip():
        errs.append("mpn is required")

    url = rec.get("source_url")
    if not isinstance(url, str) or urllib.parse.urlsplit(url).scheme != "https":
        errs.append("source_url must be an https URL")
    elif isinstance(sid, str) and sid in suppliers and not _host_allowed(url, suppliers[sid][1]):
        errs.append(f"source_url host is not on {sid}'s domain ({', '.join(suppliers[sid][1])})")

    ts = parse_timestamp(rec.get("verified_at"))
    if ts is None:
        errs.append("verified_at must be an ISO 8601 timestamp with a timezone, e.g. 2026-11-21T10:00:00Z")
    elif now is not None and ts > now + 300:
        errs.append("verified_at is in the future")

    stock = rec.get("stock")
    if stock is not None and not (isinstance(stock, int) and not isinstance(stock, bool) and stock >= 0):
        errs.append("stock must be an integer >= 0 or null")
    price = rec.get("price")
    if price is not None and not (_is_number(price) and price > 0):
        errs.append("price must be a number > 0 or null")
    breaks = rec.get("price_breaks") or []
    if not isinstance(breaks, list):
        errs.append("price_breaks must be a list")
    else:
        for i, pb in enumerate(breaks):
            if not (isinstance(pb, dict) and isinstance(pb.get("quantity"), int) and pb["quantity"] >= 1
                    and _is_number(pb.get("unit_price")) and pb["unit_price"] > 0):
                errs.append(f"price_breaks[{i}] needs integer quantity >= 1 and unit_price > 0")
    if price is not None or breaks:
        cur = rec.get("currency")
        if not isinstance(cur, str) or not _CURRENCY.match(cur):
            errs.append("currency (ISO 4217, e.g. USD, INR) is required when a price is given")
    if "backorder" in rec and not isinstance(rec["backorder"], bool):
        errs.append("backorder must be true or false")
    lt = rec.get("lead_time_days")
    if lt is not None and not (isinstance(lt, int) and not isinstance(lt, bool) and lt >= 0):
        errs.append("lead_time_days must be an integer >= 0 or null")
    if "specs" in rec and not isinstance(rec["specs"], dict):
        errs.append("specs must be an object")
    ac = rec.get("assembly_class") or ""
    if ac and ac not in _ASSEMBLY_CLASSES:
        errs.append(f"assembly_class must be one of {', '.join(_ASSEMBLY_CLASSES)}")
    return errs


def record_to_offer(rec: Dict[str, Any], suppliers: Optional[Dict[str, Tuple[str, Tuple[str, ...]]]] = None) -> SupplierOffer:
    """Convert a *validated* record into a SupplierOffer (agent_evidence provenance)."""
    suppliers = DEFAULT_SUPPLIERS if suppliers is None else suppliers
    sid = rec["supplier_id"]
    mpn = rec["mpn"].strip()
    mfr = (rec.get("manufacturer") or "").strip()
    currency = rec.get("currency") or "USD"
    breaks = sorted(
        (PriceBreak(quantity=pb["quantity"], unit_price=float(pb["unit_price"]), currency=currency)
         for pb in (rec.get("price_breaks") or [])),
        key=lambda p: p.quantity,
    )
    price = rec.get("price")
    unit = float(price) if price is not None else (breaks[0].unit_price if breaks else 0.0)
    stock = rec.get("stock")
    desk_id = ComponentIdentityResolver.generate_desk_id(
        ComponentIdentityResolver.normalize_manufacturer(mfr or "Generic"),
        ComponentIdentityResolver.normalize_mpn(mpn),
    )
    return SupplierOffer(
        supplier_id=sid,
        supplier_name=suppliers.get(sid, (sid, ()))[0],
        sku=(rec.get("sku") or mpn).strip(),
        canonical_desk_id=desk_id,
        manufacturer_name=mfr,
        mpn=mpn,
        product_url=rec["source_url"],
        datasheet_url=rec.get("datasheet_url"),
        description=rec.get("description") or "",
        package=rec.get("package") or "",
        stock=int(stock) if stock is not None else 0,
        currency=currency,
        unit_price=unit,
        price_breaks=breaks,
        moq=int(rec.get("moq") or 1),
        lead_time_days=rec.get("lead_time_days"),
        last_checked_ts=parse_timestamp(rec["verified_at"]) or 0.0,
        raw_payload=dict(rec),
        availability_source=SOURCE_AGENT_EVIDENCE,
        stock_known=stock is not None,
        lifecycle=rec.get("lifecycle") or "",
        backorder=bool(rec.get("backorder", False)),
        footprint=rec.get("footprint") or "",
        specs=dict(rec.get("specs") or {}),
        alternative_for=(rec.get("alternative_for") or "").strip(),
        assembly_class=rec.get("assembly_class") or "",
    )


@dataclass
class IngestReport:
    accepted: int = 0
    rejected: List[Dict[str, Any]] = field(default_factory=list)  # {"source", "index", "mpn", "errors"}

    def to_dict(self) -> Dict[str, Any]:
        return {"accepted": self.accepted, "rejected": list(self.rejected)}


def _key(s: str) -> str:
    return re.sub(r"\s+", "", s or "").upper()


class EvidenceStore:
    """Validated evidence offers, keyed by (supplier_id, sku); the newest verification wins."""

    def __init__(self, suppliers: Optional[Dict[str, Tuple[str, Tuple[str, ...]]]] = None) -> None:
        self.suppliers = dict(DEFAULT_SUPPLIERS if suppliers is None else suppliers)
        self._offers: Dict[Tuple[str, str], SupplierOffer] = {}

    def add_record(self, rec: Any, now: Optional[float] = None) -> List[str]:
        errs = validate_record(rec, self.suppliers, now=now)
        if errs:
            return errs
        off = record_to_offer(rec, self.suppliers)
        k = (off.supplier_id, _key(off.sku))
        old = self._offers.get(k)
        if old is None or off.last_checked_ts >= old.last_checked_ts:
            self._offers[k] = off
        return []

    def ingest(self, payload: Any, source: str = "<memory>", now: Optional[float] = None) -> IngestReport:
        rep = IngestReport()
        if isinstance(payload, dict):
            schema = payload.get("schema")
            if schema not in (None, EVIDENCE_SCHEMA):
                rep.rejected.append({"source": source, "index": None, "mpn": "",
                                     "errors": [f"unknown schema {schema!r}; expected {EVIDENCE_SCHEMA}"]})
                return rep
            records = payload.get("records")
        else:
            records = payload
        if not isinstance(records, list):
            rep.rejected.append({"source": source, "index": None, "mpn": "",
                                 "errors": ["evidence must be a list of records or {\"records\": [...]}"]})
            return rep
        for i, rec in enumerate(records):
            errs = self.add_record(rec, now=now)
            if errs:
                mpn = rec.get("mpn", "") if isinstance(rec, dict) else ""
                rep.rejected.append({"source": source, "index": i, "mpn": mpn, "errors": errs})
            else:
                rep.accepted += 1
        return rep

    def load_file(self, path: str, now: Optional[float] = None) -> IngestReport:
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, ValueError) as e:
            rep = IngestReport()
            rep.rejected.append({"source": path, "index": None, "mpn": "", "errors": [f"cannot read: {e}"]})
            return rep
        return self.ingest(payload, source=path, now=now)

    def offers(self, supplier_id: Optional[str] = None) -> List[SupplierOffer]:
        out = [o for (sid, _), o in self._offers.items() if supplier_id is None or sid == supplier_id]
        return sorted(out, key=lambda o: (o.supplier_id, _key(o.mpn), _key(o.sku)))

    def __len__(self) -> int:
        return len(self._offers)


class EvidenceSupplierProvider(SupplierProvider):
    """Serves one supplier's offers from an EvidenceStore (no network)."""

    def __init__(self, supplier_id: str, name: str, store: EvidenceStore,
                 capabilities: Optional[SupplierCapabilities] = None) -> None:
        caps = capabilities or SupplierCapabilities(
            search=True, product_details=True, pricing=True, inventory=True,
            datasheet_links=True, ordering=False, package_filter=True, category_filter=False,
        )
        super().__init__(supplier_id=supplier_id, name=name, capabilities=caps)
        self.store = store

    def _mine(self) -> List[SupplierOffer]:
        return self.store.offers(self.supplier_id)

    def search_components(self, query: str, filters: Optional[Dict[str, Any]] = None,
                          limit: int = 20) -> List[SupplierOffer]:
        q = _key(query)
        pkg = _key(str(filters["package"])) if filters and "package" in filters else None
        out = []
        for o in self._mine():
            if q and q not in _key(o.mpn) and q not in _key(o.sku) and q not in _key(o.description):
                continue
            if pkg is not None and _key(o.package) != pkg:
                continue
            out.append(o)
            if len(out) >= limit:
                break
        return out

    def get_component(self, supplier_part_number: str) -> Optional[SupplierOffer]:
        k = _key(supplier_part_number)
        return next((o for o in self._mine() if _key(o.sku) == k), None)

    def get_offers(self, mpn: str) -> List[SupplierOffer]:
        k = _key(mpn)
        return [o for o in self._mine() if _key(o.mpn) == k]

    def get_alternative_offers(self, mpn: str) -> List[SupplierOffer]:
        k = _key(mpn)
        return [o for o in self._mine() if o.alternative_for and _key(o.alternative_for) == k]
