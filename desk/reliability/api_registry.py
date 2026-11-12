"""Version-aware registry of what the EasyEDA Pro API has actually been observed to do.

A capability is never inferred from a method name. Each entry records the document type it was used on, the
EasyEDA version where known, read/write class, the parameters that were tried, the return shape, the independent
verification that proves the call did what it claims, known limitations, and a status:

    VERIFIED      observed to perform the operation, with a readback that proved it (evidence cited)
    EXPERIMENTAL  observed to run, but with side effects or limits that make the return value untrustworthy
    DIALOG        the call only opens a dialog; completion needs a human and the return value means nothing
    UNSUPPORTED   observed not to work (hangs, no effect, wrong target)
    UNKNOWN       never exercised; the default for any method not listed

`verification_contract(method)` returns the operation-specific postcondition check the mutation layer must run.
There is deliberately no generic "returned true" contract.

Evidence sources: learning/incidents (INC-*), live-test/ups-1000 failure register (F-*), desk/routing/pipeline.py.
Zero external dependencies.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

from desk.reliability.models import VerificationResult


class CapabilityStatus(str, enum.Enum):
    VERIFIED = "VERIFIED"
    EXPERIMENTAL = "EXPERIMENTAL"
    DIALOG = "DIALOG"
    UNSUPPORTED = "UNSUPPORTED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ApiCapability:
    method: str
    document_types: Sequence[str]            # "pcb", "schematic", "project", "panel", "any"
    rw: str                                  # "read" | "write" | "dialog"
    status: CapabilityStatus
    verifier: str                            # name of a verification contract, "" for reads
    expected_return: str = ""
    tested_params: Sequence[str] = ()
    easyeda_versions: Sequence[str] = ()     # e.g. ("3.2.149",) when known
    limitations: Sequence[str] = ()
    evidence: Sequence[str] = ()             # incident / failure-register ids

    def to_dict(self) -> Dict[str, Any]:
        return {"method": self.method, "document_types": list(self.document_types), "rw": self.rw, "status": self.status.value,
                "verifier": self.verifier, "expected_return": self.expected_return, "tested_params": list(self.tested_params),
                "easyeda_versions": list(self.easyeda_versions), "limitations": list(self.limitations), "evidence": list(self.evidence)}


# ------------------------------------------------------------------------------------------------ verifiers
def _count_increased(before: Any, after: Any, expected: Any) -> VerificationResult:
    v = VerificationResult()
    want = int(expected.get("min_count", 1)) if isinstance(expected, dict) else int(expected or 1)
    v.add("count_after_at_least", want, after, ok=isinstance(after, int) and after >= want)
    v.add("count_changed", f"> {before}", after, ok=isinstance(after, int) and isinstance(before, int) and after > before)
    return v


def _ids_absent(before: Any, after: Any, expected: Any) -> VerificationResult:
    v = VerificationResult()
    ids = set(expected.get("ids", [])) if isinstance(expected, dict) else set(expected or [])
    present = set(after or [])
    survivors = sorted(ids & present)
    v.add("deleted_ids_absent_from_readback", [], survivors, ok=not survivors,
          note="primitives that still exist after delete() returned true (INC-20261112-012)")
    return v


def _ids_present(before: Any, after: Any, expected: Any) -> VerificationResult:
    v = VerificationResult()
    ids = set(expected.get("ids", [])) if isinstance(expected, dict) else set(expected or [])
    present = set(after or [])
    missing = sorted(ids - present)
    v.add("created_ids_present_in_readback", [], missing, ok=not missing)
    return v


def _document_uuid(before: Any, after: Any, expected: Any) -> VerificationResult:
    v = VerificationResult()
    want = expected.get("document_uuid") if isinstance(expected, dict) else expected
    v.add("active_document_uuid", want, after)
    return v


def _coordinates(before: Any, after: Any, expected: Any) -> VerificationResult:
    """expected = {"x":..,"y":..,"tol":..}; after = {"x":..,"y":..}"""
    v = VerificationResult()
    tol = float(expected.get("tol", 0.01)) if isinstance(expected, dict) else 0.01
    ok = isinstance(after, dict) and all(abs(float(after.get(k, 1e9)) - float(expected[k])) <= tol for k in ("x", "y"))
    v.add("coordinates_within_tolerance", {k: expected.get(k) for k in ("x", "y")} if isinstance(expected, dict) else expected, after, ok=ok)
    return v


def _copper_counts(before: Any, after: Any, expected: Any) -> VerificationResult:
    """SES import: tracks and vias must be present and the document must be the bound one.
    expected = {"min_tracks": n, "document_uuid": u}; after = {"tracks": n, "vias": m, "document_uuid": u}"""
    v = VerificationResult()
    after = after or {}
    v.add("tracks_after_at_least", expected.get("min_tracks", 1), after.get("tracks"),
          ok=isinstance(after.get("tracks"), int) and after["tracks"] >= int(expected.get("min_tracks", 1)))
    if expected.get("document_uuid"):
        v.add("document_uuid", expected["document_uuid"], after.get("document_uuid"))
    if "min_vias" in expected:
        v.add("vias_after_at_least", expected["min_vias"], after.get("vias"),
              ok=isinstance(after.get("vias"), int) and after["vias"] >= int(expected["min_vias"]))
    return v


def _pin_net_map(before: Any, after: Any, expected: Any) -> VerificationResult:
    """Schematic->PCB sync: component count AND the pad/net map must match the schematic netlist.
    expected = {"components": n, "pad_nets": {"R1.1": "GND", ...}}; after = {"components": n, "pad_nets": {...}}"""
    v = VerificationResult()
    after = after or {}
    v.add("pcb_component_count", expected.get("components"), after.get("components"))
    want = expected.get("pad_nets") or {}
    got = after.get("pad_nets") or {}
    mismatches = sorted(k for k in want if got.get(k) != want[k])
    v.add("pad_net_mismatches", [], mismatches[:20], ok=not mismatches, note=f"{len(mismatches)} mismatching pads")
    return v


def _value_equals(before: Any, after: Any, expected: Any) -> VerificationResult:
    v = VerificationResult()
    v.add("readback_equals_expected", expected, after)
    return v


def _pour_present(before: Any, after: Any, expected: Any) -> VerificationResult:
    """expected = {"net": "GND", "layer": 1}; after = list of {"id","net","layer"} pours read back."""
    v = VerificationResult()
    hits = [p for p in (after or []) if p.get("net") == expected.get("net") and int(p.get("layer", -1)) == int(expected.get("layer", -2))]
    v.add("pour_primitive_for_net_on_layer", expected, [p.get("id") for p in hits], ok=bool(hits))
    return v


VERIFIERS: Dict[str, Callable[[Any, Any, Any], VerificationResult]] = {
    "count_increased": _count_increased,
    "ids_absent": _ids_absent,
    "ids_present": _ids_present,
    "document_uuid": _document_uuid,
    "coordinates": _coordinates,
    "copper_counts": _copper_counts,
    "pin_net_map": _pin_net_map,
    "value_equals": _value_equals,
    "pour_present": _pour_present,
}


def verify(contract: str, before: Any, after: Any, expected: Any) -> VerificationResult:
    """Run a named verification contract. An unknown contract fails closed (no checks -> not passed)."""
    fn = VERIFIERS.get(contract)
    if fn is None:
        v = VerificationResult()
        v.add("verification_contract_known", contract, None, ok=False, note="no verifier registered; cannot prove the mutation")
        return v
    return fn(before, after, expected)


# ------------------------------------------------------------------------------------------------ registry
_V = CapabilityStatus
CAPABILITIES: Dict[str, ApiCapability] = {c.method: c for c in (
    # ---- reads that prove identity --------------------------------------------------------------------------
    ApiCapability("eda.dmt_SelectControl.getCurrentDocumentInfo", ("any",), "read", _V.VERIFIED, "",
                  expected_return="{uuid, docType, ...} of the ACTIVE document in the addressed window",
                  easyeda_versions=("3.2.149",), evidence=("desk/bridge.py guard()", "INC-20261112-013")),
    ApiCapability("eda.dmt_Project.getCurrentProjectInfo", ("any",), "read", _V.VERIFIED, "",
                  expected_return="{uuid, friendlyName, ...} of the project open in the addressed window",
                  easyeda_versions=("3.2.149",), evidence=("UPS_1000 F-001/F-002 rebind.py", "INC-20261112-013")),
    ApiCapability("eda.dmt_EditorControl.openDocument", ("any",), "write", _V.VERIFIED, "document_uuid",
                  expected_return="undefined; verify with getCurrentDocumentInfo().uuid after a short delay",
                  limitations=("first open after a reload can take > 2 min; poll (KF-20261112-008)",
                               "runs in the ADDRESSED window: an unbound call opens the document in a foreign project"),
                  evidence=("KF-20261112-008", "INC-20261112-011")),
    # ---- primitives ------------------------------------------------------------------------------------------
    ApiCapability("eda.pcb_PrimitiveComponent.getAll", ("pcb",), "read", _V.VERIFIED, "",
                  expected_return="array of components", evidence=("UPS_1000 F-004 readback", "tools/pcb_dump.py")),
    ApiCapability("eda.pcb_PrimitiveLine.getAll", ("pcb",), "read", _V.VERIFIED, "", evidence=("desk/routing/pipeline.py",)),
    ApiCapability("eda.pcb_PrimitiveVia.getAll", ("pcb",), "read", _V.VERIFIED, "", evidence=("desk/routing/pipeline.py",)),
    ApiCapability("eda.pcb_PrimitivePad.getAll", ("pcb",), "read", _V.VERIFIED, "", evidence=("desk/routing/pipeline.py",)),
    ApiCapability("eda.pcb_PrimitiveLine.delete", ("pcb",), "write", _V.EXPERIMENTAL, "ids_absent",
                  expected_return="true even when primitives survive", tested_params=("array of primitiveId, batches of 150",),
                  limitations=("33 of 1360 tracks survived a delete that returned true (INC-20261112-012); detach the net first",
                               "a batch of > ~150 ids approaches the 120 s gateway cap"),
                  evidence=("INC-20261112-012",)),
    ApiCapability("eda.pcb_PrimitiveVia.delete", ("pcb",), "write", _V.VERIFIED, "ids_absent",
                  expected_return="true", tested_params=("array of primitiveId",), evidence=("INC-20261112-012",)),
    ApiCapability("eda.pcb_PrimitiveLine.modify", ("pcb",), "write", _V.VERIFIED, "value_equals",
                  expected_return="true", tested_params=("id, {lineWidth}", "id, {net:''}"),
                  evidence=("desk/routing/pipeline.py phase 16", "INC-20261112-012")),
    ApiCapability("eda.pcb_PrimitiveComponent.modify", ("pcb",), "write", _V.VERIFIED, "coordinates",
                  expected_return="true", tested_params=("id, {x, y, rotation}",), evidence=("tools/pcb_place.py",)),
    ApiCapability("eda.pcb_PrimitivePour.getAll", ("pcb",), "read", _V.VERIFIED, "", evidence=("INC-20251111-006",),
                  limitations=("pcb_PrimitivePoured has no getState_Net; use pourPrimitiveId / pourFills",)),
    ApiCapability("eda.pcb_PrimitivePour.create", ("pcb",), "write", _V.EXPERIMENTAL, "pour_present",
                  limitations=("live pour creation IMPLEMENTED_UNVERIFIED (docs/engineering/COPPER_ZONE_GENERATION.md)",
                               "modify(complexPolygon) does not move a pour; recreate instead (KF-20251111-004)"),
                  evidence=("docs/engineering/COPPER_ZONE_GENERATION.md", "KF-20251111-004")),
    # ---- document-level operations ---------------------------------------------------------------------------
    ApiCapability("eda.pcb_Document.importChanges", ("pcb",), "dialog", _V.DIALOG, "pin_net_map",
                  expected_return="true as soon as the Import Changes dialog opens; nothing is applied",
                  tested_params=("()", "(schematic uuid)", "(sheet uuid)"),
                  limitations=("the dialog lists nothing unless sch_Document.save() ran first",
                               "component count stays 0 until a human clicks Apply (UPS_1000 F-004, 8 s and 30 s readbacks)"),
                  evidence=("INC-20261111-006", "UPS_1000 F-004")),
    ApiCapability("eda.pcb_Net.setNetlist", ("pcb",), "write", _V.EXPERIMENTAL, "pin_net_map",
                  expected_return="true; assigns nets to EXISTING footprints only, instantiates no component",
                  tested_params=("'JLCEDA', <schematic netlist 285 kB>",), evidence=("UPS_1000 F-004",)),
    ApiCapability("eda.pcb_Document.importAutoRouteSesFile", ("pcb",), "write", _V.VERIFIED, "copper_counts",
                  expected_return="true", tested_params=("File([bytes], 'desk_route.ses')",),
                  limitations=("rewrites widths and inner layers of imported wires (INC-20261112-010); widen after import",),
                  evidence=("desk/routing/pipeline.py phase 15", "INC-20261112-010", "WATCH rev B release")),
    ApiCapability("eda.pcb_Document.save", ("pcb",), "write", _V.VERIFIED, "", evidence=("desk/routing/pipeline.py",),
                  limitations=("no readback exists for a save; the evidence is the next getter returning the saved content",)),
    ApiCapability("eda.sch_Document.save", ("schematic",), "write", _V.VERIFIED, "", evidence=("INC-20261111-006",),
                  limitations=("no readback exists for a save; importChanges lists nothing unless the schematic was saved",)),
    ApiCapability("eda.pcb_ManufactureData.getDsnFile", ("pcb",), "read", _V.VERIFIED, "",
                  expected_return="File (undefined when the outline is not one closed primitive)",
                  limitations=("36 outline segments -> undefined; a long vertex list hangs EasyEDA (KF-20261111-007)",),
                  evidence=("KF-20261111-007", "INC-20261111-008")),
    ApiCapability("eda.pcb_ManufactureData.clearRouting", ("pcb",), "dialog", _V.DIALOG, "copper_counts",
                  limitations=("behaves like a dialog; hangs to the 120 s gateway cap (INC-20261112-012)",),
                  evidence=("INC-20261112-012",)),
    ApiCapability("eda.pcb_Drc.check", ("pcb",), "read", _V.EXPERIMENTAL, "",
                  limitations=("stalls past the 120 s cap on routed boards (> 12 min, INC-20261112-012/013); GUI DRC by the Captain",),
                  evidence=("INC-20261112-012", "INC-20261112-013")),
    ApiCapability("eda.dmt_Pcb.modifyPcbName", ("project",), "write", _V.UNSUPPORTED, "value_equals",
                  expected_return="true while renaming a DIFFERENT PCB", evidence=("INC-20261111-005",)),
    ApiCapability("eda.pcb_DrcRule.overwriteCurrentRuleConfiguration", ("pcb",), "write", _V.UNSUPPORTED, "value_equals",
                  expected_return="undefined/false, no effect", evidence=("INC-20261111-006",)),
    ApiCapability("eda.pcb_DrcRule.saveRuleConfiguration", ("pcb",), "write", _V.UNSUPPORTED, "value_equals",
                  expected_return="undefined/false, no effect", evidence=("INC-20261111-006",)),
    ApiCapability("eda.pcb_DrcRule.overwriteNetRules", ("pcb",), "write", _V.VERIFIED, "value_equals",
                  evidence=("INC-20261111-006 (readback + negative DRC test)",)),
    ApiCapability("eda.sch_Netlist.getNetlist", ("schematic",), "read", _V.UNSUPPORTED, "",
                  limitations=("hung for 120 s (UPS_1000 F-004)",), evidence=("UPS_1000 F-004",)),
    ApiCapability("eda.sch_ManufactureData.getNetlistFile", ("schematic",), "read", _V.VERIFIED, "",
                  evidence=("UPS_1000 F-004",)),
    ApiCapability("eda.lib_Device.search", ("any",), "read", _V.VERIFIED, "", evidence=("tools/resolve.py",)),
    ApiCapability("eda.dmt_Panel.createPanel", ("panel",), "write", _V.VERIFIED, "ids_present",
                  limitations=("layer-11 region only on Panel documents (KF-20251111-002)",), evidence=("INC-20251111-002",)),
)}

DIALOG_METHODS = {m for m, c in CAPABILITIES.items() if c.status == CapabilityStatus.DIALOG}


def capability(method: str) -> ApiCapability:
    """Registry entry for `method` (with or without the `eda.` prefix). Unknown methods are UNKNOWN, not inferred."""
    m = method if method.startswith("eda.") else "eda." + method
    return CAPABILITIES.get(m) or ApiCapability(m, ("any",), "unknown", CapabilityStatus.UNKNOWN, "",
                                                 limitations=("never exercised by DESK; do not assume support",))


def verification_contract(method: str) -> str:
    return capability(method).verifier


def methods_in(code: str) -> List[str]:
    """The `eda.<module>.<method>` calls that appear in a JS snippet (for journal and registry lookups)."""
    import re
    return sorted(set(re.findall(r"\beda\.[A-Za-z_]+\.[A-Za-z_]+", code or "")))


def riskiest_status(code: str) -> CapabilityStatus:
    """The least trustworthy status among the methods a snippet calls (UNKNOWN when it calls nothing known)."""
    order = [CapabilityStatus.UNSUPPORTED, CapabilityStatus.DIALOG, CapabilityStatus.UNKNOWN, CapabilityStatus.EXPERIMENTAL,
             CapabilityStatus.VERIFIED]
    found = [capability(m).status for m in methods_in(code)]
    if not found:
        return CapabilityStatus.UNKNOWN
    for s in order:
        if s in found:
            return s
    return CapabilityStatus.UNKNOWN


def as_rows() -> List[Dict[str, Any]]:
    return [c.to_dict() for c in sorted(CAPABILITIES.values(), key=lambda c: c.method)]
