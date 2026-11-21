"""Deterministic in-stock-first component selection and the verified selection report (roadmap I-5).

For each BOM line (parts grouped by MPN) the selector:

1. collects offers for the designed MPN from every registered supplier (and the line's LCSC code);
2. collects alternative candidates (``alternatives`` listed on the part, and offers suppliers or
   evidence propose with ``alternative_for``), each checked for package/footprint and
   electrical/mechanical equivalence (``equivalence``);
3. classifies every offer with ``inventory.classify_offer`` (unverified -> STOCK_UNKNOWN);
4. ranks the selectable ones with a fixed key and picks the first.

Ranking key, in order (lower wins; fully deterministic, ties end on supplier id and SKU):

    designed MPN before alternatives
    -> verified in stock at a preferred supplier (Robu, LCSC by default)
    -> verified in stock at another supplier
    -> backordered at a preferred / other supplier (ONLY when SourcingPolicy.allow_backorder)
    -> IN_STOCK_CONFIRMED before LOW_STOCK
    -> lifecycle ACTIVE before UNKNOWN before NRND
    -> unit price for the required quantity, in the base currency (unconvertible -> last)
    -> lead time -> preferred-supplier order -> supplier id -> SKU

Never selectable: OUT_OF_STOCK, DISCONTINUED, STOCK_UNKNOWN, LOW_STOCK that does not cover the
quantity, BACKORDERED without the client permission flag, an offer whose package contradicts the
design, and an alternative that is not COMPATIBLE on both footprint and electrical checks.
JLCPCB parts-library rows are used for the assembly assessment only, not as a purchase source.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from desk.component_intelligence.procurement.equivalence import (
    MECHANICAL_KEYS,
    Equivalence,
    EquivalenceResult,
    check_electrical,
    check_footprint,
    requirement_from_part,
)
from desk.component_intelligence.procurement.inventory import (
    DEFAULT_LOW_STOCK_MULTIPLIER,
    DEFAULT_MAX_AGE_DAYS,
    InventoryAssessment,
    InventoryState,
    Lifecycle,
    classify_offer,
)
from desk.component_intelligence.suppliers.evidence import format_timestamp
from desk.component_intelligence.suppliers.models import SupplierOffer
from desk.component_intelligence.suppliers.registry import SupplierRegistry

REPORT_SCHEMA = "desk.sourcing.report/1"
_LIFECYCLE_RANK = {Lifecycle.ACTIVE: 0, Lifecycle.UNKNOWN: 1, Lifecycle.NRND: 2, Lifecycle.DISCONTINUED: 3}
_INF = float("inf")


@dataclass
class SourcingPolicy:
    preferred_suppliers: Tuple[str, ...] = ("robu", "lcsc")
    allow_backorder: bool = False          # explicit client permission; default refuses backorders
    max_age_days: float = DEFAULT_MAX_AGE_DAYS
    low_stock_multiplier: float = DEFAULT_LOW_STOCK_MULTIPLIER
    assembly_supplier: str = "jlcpcb"
    base_currency: str = "USD"
    fx_to_base: Dict[str, float] = field(default_factory=dict)  # e.g. {"INR": 0.012}; caller-supplied

    def to_dict(self) -> Dict[str, Any]:
        return {
            "preferred_suppliers": list(self.preferred_suppliers),
            "allow_backorder": self.allow_backorder,
            "max_age_days": self.max_age_days,
            "low_stock_multiplier": self.low_stock_multiplier,
            "assembly_supplier": self.assembly_supplier,
            "base_currency": self.base_currency,
            "fx_to_base": dict(self.fx_to_base),
        }


@dataclass
class BomLineRequest:
    mpn: str
    refs: List[str]
    required_quantity: int
    manufacturer: str = ""
    package: str = ""
    footprint: str = ""
    lcsc: str = ""
    requirement: Dict[str, Any] = field(default_factory=dict)   # electrical requirement
    design_specs: Dict[str, Any] = field(default_factory=dict)  # mechanical: pin_count, body_*_mm, ...
    alternatives: List[str] = field(default_factory=list)       # alternative MPNs named in the spec

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mpn": self.mpn, "refs": sorted(self.refs), "required_quantity": self.required_quantity,
            "manufacturer": self.manufacturer, "package": self.package, "footprint": self.footprint,
            "lcsc": self.lcsc, "requirement": dict(self.requirement),
            "design_specs": dict(self.design_specs), "alternatives": list(self.alternatives),
        }


def group_parts(parts: Sequence[Dict[str, Any]], batch_quantity: int = 1) -> List[BomLineRequest]:
    """Group block-spec / BOM parts by MPN into line requests (sorted by MPN)."""
    lines: Dict[str, BomLineRequest] = {}
    for p in parts:
        mpn = str(p.get("mpn") or "").strip()
        if not mpn or mpn == "?":
            continue
        ln = lines.get(mpn)
        if ln is None:
            specs = dict(p.get("specs") or {})
            alts = p.get("alternatives") or p.get("alternates") or []
            ln = lines[mpn] = BomLineRequest(
                mpn=mpn, refs=[], required_quantity=0,
                manufacturer=str(p.get("manufacturer") or p.get("mfr") or ""),
                package=str(p.get("package") or ""), footprint=str(p.get("footprint") or ""),
                lcsc=str(p.get("lcsc") or "").strip(),
                requirement=requirement_from_part(p),
                design_specs={k: specs[k] for k in MECHANICAL_KEYS if k in specs},
                alternatives=[str(a).strip() for a in alts if str(a).strip()],
            )
        ln.refs.append(str(p.get("ref") or ""))
    for ln in lines.values():
        ln.required_quantity = max(1, len(ln.refs)) * max(1, int(batch_quantity))
    return [lines[k] for k in sorted(lines)]


@dataclass
class Candidate:
    offer: SupplierOffer
    assessment: InventoryAssessment
    is_alternative: bool
    footprint: EquivalenceResult
    electrical: Optional[EquivalenceResult]     # None for the designed MPN itself
    selectable: bool
    rejected_because: List[str]
    unit_price: Optional[float]                 # for the required quantity, offer currency
    unit_price_base: Optional[float]            # converted to policy.base_currency, if possible

    def to_dict(self) -> Dict[str, Any]:
        o = self.offer
        return {
            "supplier_id": o.supplier_id, "supplier": o.supplier_name, "sku": o.sku, "mpn": o.mpn,
            "manufacturer": o.manufacturer_name, "package": o.package, "footprint_name": o.footprint,
            "source_url": o.product_url,
            "verified_at": format_timestamp(o.last_checked_ts) if o.last_checked_ts else "",
            "availability_source": o.availability_source,
            "inventory": self.assessment.to_dict(),
            "unit_price": self.unit_price, "currency": o.currency if self.unit_price is not None else "",
            "unit_price_base": self.unit_price_base,
            "lead_time_days": o.lead_time_days, "datasheet_url": o.datasheet_url or "",
            "is_alternative": self.is_alternative,
            "footprint": self.footprint.to_dict(),
            "electrical": self.electrical.to_dict() if self.electrical else None,
            "selectable": self.selectable, "rejected_because": list(self.rejected_because),
        }


@dataclass
class SourcingLine:
    request: BomLineRequest
    status: str                    # SELECTED | SELECTED_ALTERNATIVE | SELECTED_BACKORDER | UNRESOLVED
    selected: Optional[Candidate]
    candidates: List[Candidate]
    selection_reason: str
    assembly: Dict[str, Any]
    limitations: List[str]
    assessed_at: float

    @property
    def in_stock(self) -> bool:
        return self.selected is not None and self.selected.assessment.in_stock

    @property
    def compatible_alternatives(self) -> List[Candidate]:
        return [c for c in self.candidates if c.is_alternative
                and c.footprint.verdict is Equivalence.COMPATIBLE
                and c.electrical is not None and c.electrical.verdict is Equivalence.COMPATIBLE]

    def snapshot(self) -> Dict[str, Any]:
        """Supplier, URL, timestamp and stock this line rests on (selected, else best evaluated)."""
        c = self.selected or (self.candidates[0] if self.candidates else None)
        if c is None:
            return {"supplier_id": "", "supplier": "NONE", "sku": "", "source_url": "",
                    "verified_at": format_timestamp(self.assessed_at), "stock": None,
                    "state": InventoryState.STOCK_UNKNOWN.value,
                    "note": "no offer found at any registered supplier"}
        d = c.to_dict()
        return {"supplier_id": d["supplier_id"], "supplier": d["supplier"], "sku": d["sku"],
                "source_url": d["source_url"], "verified_at": d["verified_at"],
                "stock": c.assessment.stock, "state": c.assessment.state.value,
                "note": "selected" if self.selected else "best evaluated offer (not selectable)"}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request": self.request.to_dict(),
            "status": self.status,
            "in_stock": self.in_stock,
            "selection_reason": self.selection_reason,
            "selected": self.selected.to_dict() if self.selected else None,
            "snapshot": self.snapshot(),
            "candidates": [c.to_dict() for c in self.candidates],
            "compatible_alternatives": [f"{c.offer.supplier_id}:{c.offer.sku} ({c.offer.mpn})"
                                        for c in self.compatible_alternatives],
            "assembly": self.assembly,
            "limitations": list(self.limitations),
        }


def _norm(s: str) -> str:
    return "".join((s or "").split()).upper()


def _price_base(price: Optional[float], currency: str, policy: SourcingPolicy) -> Optional[float]:
    if price is None:
        return None
    if currency == policy.base_currency:
        return price
    rate = policy.fx_to_base.get(currency)
    return price * rate if rate else None


def _failing(res: EquivalenceResult) -> str:
    bad = [r for r in res.reasons if not (r.endswith("matches") or " >= " in r or " <= " in r
                                          or r.startswith("same "))]
    return "; ".join(bad or res.reasons)


def _evaluate(offer: SupplierOffer, req: BomLineRequest, is_alt: bool, policy: SourcingPolicy,
              now: float) -> Candidate:
    a = classify_offer(offer, req.required_quantity, now=now, max_age_days=policy.max_age_days,
                       low_stock_multiplier=policy.low_stock_multiplier)
    fp = check_footprint(req.package, offer.package, req.design_specs, offer.specs,
                         req.footprint, offer.footprint)
    el = check_electrical(req.requirement, offer.specs) if is_alt else None
    why: List[str] = []
    if a.in_stock:
        pass
    elif a.stock_state is InventoryState.BACKORDERED:
        if not policy.allow_backorder:
            why.append("backordered and the client has not permitted backorders")
    elif a.stock_state is InventoryState.LOW_STOCK:
        why.append(f"verified stock {a.stock} does not cover {a.required_quantity}")
    else:
        why.append(f"inventory {a.stock_state.value}")
    if is_alt:
        if fp.verdict is not Equivalence.COMPATIBLE:
            why.append(f"footprint {fp.verdict.value}: {_failing(fp)}")
        if el is not None and el.verdict is not Equivalence.COMPATIBLE:
            why.append(f"electrical {el.verdict.value}: {_failing(el)}")
    elif fp.verdict is Equivalence.INCOMPATIBLE:
        why.append(f"supplier listing contradicts the design package: {_failing(fp)}")
    price = offer.get_price_for_quantity(req.required_quantity) if offer.price_available() else None
    return Candidate(offer, a, is_alt, fp, el, not why, why, price,
                     _price_base(price, offer.currency, policy))


def rank_key(c: Candidate, policy: SourcingPolicy) -> Tuple[Any, ...]:
    """The documented ranking key (lower sorts first)."""
    sid = c.offer.supplier_id
    preferred = sid in policy.preferred_suppliers
    pref_idx = policy.preferred_suppliers.index(sid) if preferred else len(policy.preferred_suppliers)
    a = c.assessment
    if a.in_stock:
        tier = 0 if preferred else 1
    elif a.stock_state is InventoryState.BACKORDERED:
        tier = 2 if preferred else 3
    else:
        tier = 9
    stock_rank = 0 if a.stock_state is InventoryState.IN_STOCK_CONFIRMED else 1
    price = c.unit_price_base if c.unit_price_base is not None else _INF
    lead = c.offer.lead_time_days if c.offer.lead_time_days is not None else _INF
    return (int(c.is_alternative), tier, stock_rank, _LIFECYCLE_RANK[a.lifecycle], price, lead,
            pref_idx, sid, _norm(c.offer.sku))


def select_line(req: BomLineRequest, registry: SupplierRegistry, policy: SourcingPolicy,
                now: Optional[float] = None) -> SourcingLine:
    now = time.time() if now is None else now
    lims: List[str] = []
    asm_id = policy.assembly_supplier
    primary: Dict[Tuple[str, str], SupplierOffer] = {}
    alts: Dict[Tuple[str, str], SupplierOffer] = {}

    def put(bucket: Dict[Tuple[str, str], SupplierOffer], o: SupplierOffer) -> None:
        if o.supplier_id != asm_id:  # the assembler's rows feed the assembly assessment only
            bucket.setdefault((o.supplier_id, _norm(o.sku)), o)

    for o in registry.get_offers_for_mpn(req.mpn):
        # Providers may fall back to fuzzy matches; only the exact MPN is the designed part.
        put(primary if _norm(o.mpn) == _norm(req.mpn) else alts, o)
    if req.lcsc and ("lcsc", _norm(req.lcsc)) not in primary:
        lp = registry.get_provider("lcsc")
        o = lp.get_component(req.lcsc) if lp is not None else None
        if o is not None and _norm(o.mpn) == _norm(req.mpn):
            put(primary, o)
        elif o is not None:
            lims.append(f"LCSC code {req.lcsc} is listed as {o.mpn}, not {req.mpn}; evaluated as an alternative.")
            put(alts, o)
    for o in registry.get_alternative_offers_for_mpn(req.mpn):
        put(alts, o)
    for alt_mpn in req.alternatives:
        for o in registry.get_offers_for_mpn(alt_mpn):
            if _norm(o.mpn) == _norm(alt_mpn):
                put(alts, o)
    for k in list(alts):
        if k in primary or _norm(alts[k].mpn) == _norm(req.mpn):
            alts.pop(k)

    cands = [_evaluate(o, req, False, policy, now) for o in primary.values()]
    cands += [_evaluate(o, req, True, policy, now) for o in alts.values()]
    cands.sort(key=lambda c: rank_key(c, policy))
    for c in cands:
        for lim in c.assessment.limitations:
            if lim not in lims:
                lims.append(lim)

    chosen = next((c for c in cands if c.selectable), None)
    if not primary:
        lims.append(f"No offer for {req.mpn} at any registered supplier.")
    if chosen is None:
        status = "UNRESOLVED"
        if any(c.assessment.stock_state is InventoryState.BACKORDERED for c in cands) and not policy.allow_backorder:
            reason = "no verified in-stock offer; a backorder exists but the client has not permitted it"
        elif cands:
            reason = "no verified in-stock offer and no compatible in-stock alternative"
        else:
            reason = "no offer found"
    else:
        a = chosen.assessment
        where = ("preferred supplier" if chosen.offer.supplier_id in policy.preferred_suppliers
                 else "non-preferred supplier")
        if a.stock_state is InventoryState.BACKORDERED:
            status = "SELECTED_BACKORDER"
            reason = f"backordered at {where} {chosen.offer.supplier_name}, permitted by the client flag"
        elif chosen.is_alternative:
            status = "SELECTED_ALTERNATIVE"
            reason = (f"{req.mpn} has no verified in-stock offer; {chosen.offer.mpn} is footprint- and "
                      f"electrically compatible and {a.stock_state.value} at {where} {chosen.offer.supplier_name}")
        else:
            status = "SELECTED"
            reason = f"{a.stock_state.value} at {where} {chosen.offer.supplier_name}"
        if chosen.unit_price is None:
            reason += "; price not shown"
        elif chosen.unit_price_base is None:
            lims.append(f"{chosen.offer.supplier_name} price in {chosen.offer.currency} was not compared "
                        f"(no {chosen.offer.currency}->{policy.base_currency} rate given).")

    from desk.manufacturing.jlcpcb.parts_library import assess_assembly
    pick_mpn = chosen.offer.mpn if chosen else req.mpn
    code = chosen.offer.sku if chosen and chosen.offer.supplier_id == "lcsc" else req.lcsc
    asm_provider = registry.get_provider(asm_id) if asm_id else None
    rows = asm_provider.get_offers(pick_mpn) if asm_provider is not None else []
    asm = assess_assembly(code, rows, req.required_quantity, req.package, now=now,
                          max_age_days=policy.max_age_days)
    return SourcingLine(req, status, chosen, cands, reason, asm.to_dict(), lims, now)


@dataclass
class SourcingReport:
    generated_at: float
    policy: SourcingPolicy
    lines: List[SourcingLine]
    suppliers: List[str]
    evidence: Dict[str, Any] = field(default_factory=dict)
    limitations: List[str] = field(default_factory=list)
    batch_quantity: int = 1
    project: str = ""

    def acceptance(self) -> Dict[str, Any]:
        total = len(self.lines)
        in_stock = [ln for ln in self.lines if ln.in_stock]
        with_alt = [ln for ln in self.lines if not ln.in_stock and ln.compatible_alternatives]
        failing = [ln for ln in self.lines if not ln.in_stock and not ln.compatible_alternatives]
        bo_no_flag = [ln for ln in self.lines if ln.selected is not None
                      and ln.selected.assessment.stock_state is InventoryState.BACKORDERED
                      and not self.policy.allow_backorder]
        no_prov = [ln for ln in self.lines if ln.selected is not None and not (
            ln.selected.offer.supplier_id and ln.selected.offer.product_url
            and ln.selected.offer.last_checked_ts > 0)]
        unpriced = [ln for ln in self.lines if ln.selected is not None and ln.selected.unit_price is None]
        return {
            "lines_total": total,
            "lines_in_stock": len(in_stock),
            "lines_with_compatible_alternative_only": len(with_alt),
            "lines_without_stock_or_alternative": [ln.request.mpn for ln in failing],
            "backordered_selections_without_permission": len(bo_no_flag),
            "selected_lines_missing_provenance": [ln.request.mpn for ln in no_prov],
            "selected_lines_without_price": [ln.request.mpn for ln in unpriced],
            "i5_acceptance": bool(total) and not failing and not bo_no_flag and not no_prov,
        }

    @property
    def verdict(self) -> str:
        """VERIFIED only when every line is verified in stock, priced and traceable."""
        acc = self.acceptance()
        ok = (acc["lines_total"] > 0 and acc["lines_in_stock"] == acc["lines_total"]
              and not acc["selected_lines_missing_provenance"] and not acc["selected_lines_without_price"]
              and acc["backordered_selections_without_permission"] == 0)
        return "VERIFIED" if ok else "INCOMPLETE"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": REPORT_SCHEMA,
            "project": self.project,
            "generated_at": format_timestamp(self.generated_at),
            "batch_quantity": self.batch_quantity,
            "verdict": self.verdict,
            "acceptance": self.acceptance(),
            "policy": self.policy.to_dict(),
            "suppliers": list(self.suppliers),
            "evidence": dict(self.evidence),
            "limitations": list(self.limitations),
            "lines": [ln.to_dict() for ln in self.lines],
        }

    def to_markdown(self) -> str:
        acc = self.acceptance()
        title = "# Component selection report" + (f" - {self.project}" if self.project else "")
        out = [title, "",
               f"- Generated: {format_timestamp(self.generated_at)}",
               f"- Verdict: **{self.verdict}**"
               + ("" if self.verdict == "VERIFIED" else " (not every line is verified in stock with a price)"),
               f"- Batch quantity: {self.batch_quantity}",
               f"- Suppliers searched: {', '.join(self.suppliers) or 'none'}; preferred: "
               f"{', '.join(self.policy.preferred_suppliers)}; assembly: {self.policy.assembly_supplier}",
               f"- Backorders permitted by client: {'yes' if self.policy.allow_backorder else 'no'}",
               f"- Lines in stock: {acc['lines_in_stock']}/{acc['lines_total']}; with a compatible "
               f"alternative only: {acc['lines_with_compatible_alternative_only']}; backordered "
               f"selections without permission: {acc['backordered_selections_without_permission']}",
               f"- Evidence records: {self.evidence.get('accepted', 0)} accepted, "
               f"{len(self.evidence.get('rejected', []))} rejected", ""]
        if self.limitations or acc["lines_without_stock_or_alternative"]:
            out += ["## Limitations", ""]
            for mpn in acc["lines_without_stock_or_alternative"]:
                out.append(f"- {mpn}: no verified in-stock offer and no compatible alternative.")
            out += [f"- {x}" for x in self.limitations]
            out.append("")
        out += ["## Lines", "",
                "| Refs | Qty | MPN | Status | Supplier / SKU | State | Stock | Unit price | Verified at | Source |",
                "|---|---|---|---|---|---|---|---|---|---|"]
        for ln in self.lines:
            s = ln.snapshot()
            c = ln.selected
            price = f"{c.unit_price:g} {c.offer.currency}" if c and c.unit_price is not None else "n/a"
            stock = "unknown" if s["stock"] is None else str(s["stock"])
            out.append(f"| {' '.join(sorted(ln.request.refs))} | {ln.request.required_quantity} | {ln.request.mpn} "
                       f"| {ln.status} | {s['supplier']} {s['sku']} | {s['state']} | {stock} | {price} "
                       f"| {s['verified_at']} | {s['source_url'] or '-'} |")
        out.append("")
        for ln in self.lines:
            out += [f"### {ln.request.mpn} ({' '.join(sorted(ln.request.refs))})", "",
                    f"- Decision: {ln.status} - {ln.selection_reason}"]
            asm = ln.assembly
            out.append(f"- JLCPCB assembly: {asm.get('assembly_class')} ({asm.get('class_source')})"
                       + (f", {asm['source_url']}" if asm.get("source_url") else ""))
            if ln.candidates:
                out.append("- Offers evaluated:")
                for c in ln.candidates:
                    tag = "alternative " if c.is_alternative else ""
                    verdict = "selectable" if c.selectable else "rejected: " + "; ".join(c.rejected_because)
                    extra = ""
                    if c.is_alternative:
                        extra = (f" [footprint {c.footprint.verdict.value}, electrical "
                                 f"{c.electrical.verdict.value if c.electrical else 'n/a'}]")
                    out.append(f"  - {tag}{c.offer.supplier_name} {c.offer.sku} {c.offer.mpn}: "
                               f"{c.assessment.state.value}{extra} - {verdict}")
            for lim in ln.limitations + list(asm.get("limitations", [])):
                out.append(f"- Note: {lim}")
            out.append("")
        return "\n".join(out)


def build_sourcing_report(
    parts: Sequence[Dict[str, Any]],
    registry: SupplierRegistry,
    policy: Optional[SourcingPolicy] = None,
    batch_quantity: int = 1,
    now: Optional[float] = None,
    evidence: Optional[Dict[str, Any]] = None,
    limitations: Optional[List[str]] = None,
    project: str = "",
) -> SourcingReport:
    """Select every BOM line and build the verified component selection report."""
    policy = policy or SourcingPolicy()
    now = time.time() if now is None else now
    lines = [select_line(r, registry, policy, now=now) for r in group_parts(parts, batch_quantity)]
    lims = list(limitations or [])
    for rej in (evidence or {}).get("rejected", []):
        lims.append(f"Evidence rejected ({rej.get('source')}#{rej.get('index')} {rej.get('mpn', '')}): "
                    f"{'; '.join(rej.get('errors', []))}")
    return SourcingReport(now, policy, lines,
                          sorted(p.supplier_id for p in registry.list_providers(enabled_only=True)),
                          dict(evidence or {}), lims, batch_quantity, project)
