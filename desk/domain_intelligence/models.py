"""Data contracts for the Domain Intelligence System. Zero external dependencies."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

EVIDENCE_STATES = ["DRAFT", "ADVISORY", "IMPLEMENTED", "OFFLINE_TESTED", "VERIFIED_AGAINST_SOURCE", "LIVE_VERIFIED",
                   "NEEDS_HARDWARE_VALIDATION", "BLOCKED"]
SEVERITIES = ["BLOCKING", "ERROR", "WARNING", "ADVISORY"]
CATEGORIES = ["electrical", "placement", "routing", "copper", "thermal", "emi_emc", "manufacturing"]
ENFORCEMENT_MODES = ["ENFORCED", "ADVISORY", "UNSUPPORTED"]
CLASSIFICATION_STATUSES = ["CLASSIFIED", "REVIEW_REQUIRED", "UNCLASSIFIED"]
# Outcomes of a single rule evaluation
OUTCOMES = ["PASS", "FAIL", "NOT_EVALUATED", "DEFERRED", "ADVISORY", "UNSUPPORTED"]


@dataclass
class Archetype:
    archetype_id: str
    name: str
    domain: str
    data: Dict[str, Any]

    @property
    def maturity(self) -> str:
        return str(self.data.get("maturity", {}).get("status", "DRAFT"))

    @property
    def overlays(self) -> List[str]:
        return list(self.data.get("typical_overlays", []))

    @property
    def families(self) -> List[str]:
        return list(self.data.get("typical_component_families", []))

    @property
    def required_roles(self) -> List[str]:
        return list(self.data.get("required_component_roles", []))

    @property
    def rule_ids(self) -> List[str]:
        return list(self.data.get("maturity", {}).get("rule_ids", []))

    @property
    def classification(self) -> Dict[str, Any]:
        return dict(self.data.get("classification", {}))


@dataclass
class Overlay:
    overlay_id: str
    name: str
    data: Dict[str, Any]

    @property
    def precedence(self) -> int:
        return int(self.data.get("precedence", 50))

    @property
    def applies_when(self) -> Dict[str, Any]:
        return dict(self.data.get("applies_when", {}))

    @property
    def families(self) -> List[str]:
        return list(self.data.get("adds_component_families", []))


@dataclass
class ComponentFamily:
    family_id: str
    group: str
    name: str
    data: Dict[str, Any]


@dataclass
class Rule:
    rule_id: str
    name: str
    version: str
    domain: str
    category: str
    scope: Dict[str, List[str]]
    severity: str
    applicability: Dict[str, Any]
    required_inputs: List[str]
    evaluation_method: str
    parameters: Dict[str, Any]
    source_references: List[str]
    verification_method: str
    status: str
    enforcement: Dict[str, str]
    human_review_required: bool = False
    rationale: str = ""

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Rule":
        return cls(rule_id=d["rule_id"], name=d["name"], version=d.get("version", "1.0.0"), domain=d["domain"], category=d["category"],
                   scope=d.get("scope", {}), severity=d["severity"], applicability=d.get("applicability", {}),
                   required_inputs=list(d.get("required_inputs", [])), evaluation_method=d.get("evaluation_method", "advisory"),
                   parameters=dict(d.get("parameters", {})), source_references=list(d.get("source_references", [])),
                   verification_method=d.get("verification_method", ""), status=d.get("status", "DRAFT"),
                   enforcement=dict(d.get("enforcement", {"subsystem": "none", "mode": "ADVISORY"})),
                   human_review_required=bool(d.get("human_review_required", False)), rationale=d.get("rationale", ""))

    @property
    def mode(self) -> str:
        return str(self.enforcement.get("mode", "ADVISORY"))

    @property
    def subsystem(self) -> str:
        return str(self.enforcement.get("subsystem", "none"))

    @property
    def severity_rank(self) -> int:
        return SEVERITIES.index(self.severity) if self.severity in SEVERITIES else len(SEVERITIES)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Requirements:
    """Normalised requirement features extracted deterministically from text and/or structured input."""
    text: str = ""
    features: Dict[str, Any] = field(default_factory=dict)
    provided_fields: List[str] = field(default_factory=list)
    source: str = "text"

    def get(self, key: str, default: Any = None) -> Any:
        return self.features.get(key, default)

    def to_dict(self) -> Dict[str, Any]:
        return {"features": self.features, "provided_fields": self.provided_fields, "source": self.source}


@dataclass
class Candidate:
    archetype_id: str
    domain: str
    score: float
    reasons: List[str] = field(default_factory=list)
    penalties: List[str] = field(default_factory=list)


@dataclass
class ClassificationResult:
    primary_archetype: Optional[str]
    secondary_archetypes: List[str]
    required_overlays: List[str]
    required_component_families: List[str]
    candidates: List[Candidate]
    missing_information: List[str]
    conflicts: List[str]
    confidence: float
    classification_status: str
    evidence: List[str]
    features: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["candidates"] = [asdict(c) for c in self.candidates[:10]]
        return d


@dataclass
class RuleEvaluation:
    rule_id: str
    outcome: str
    severity: str
    mode: str
    subsystem: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RuleConflict:
    rule_ids: List[str]
    parameter: str
    values: Dict[str, Any]
    resolution: str          # "stricter_kept:<rule_id>" | "review_required"
    note: str = ""


@dataclass
class Composition:
    rules: List[Rule]
    conflicts: List[RuleConflict]
    dropped: List[str]
    sources: Dict[str, List[str]]     # rule_id -> why it is in scope

    def to_dict(self) -> Dict[str, Any]:
        return {"rule_ids": [r.rule_id for r in self.rules], "conflicts": [asdict(c) for c in self.conflicts],
                "dropped": self.dropped, "sources": self.sources}


@dataclass
class CompiledDomainProfile:
    project_id: str
    primary_archetype: Optional[str]
    secondary_archetypes: List[str]
    overlays: List[str]
    component_families: List[str]
    rule_ids: List[str]
    enforced_rule_ids: List[str]
    advisory_rule_ids: List[str]
    unsupported_rule_ids: List[str]
    evaluations: List[RuleEvaluation]
    conflicts: List[RuleConflict]
    blocking_issues: List[str]
    missing_information: List[str]
    design_profile: Dict[str, Any]       # DesignProfile.to_dict() of the compiled profile (never invented values)
    status: str                          # READY | BLOCKED | REVIEW_REQUIRED
    compiled_at: str
    library_version: str

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["evaluations"] = [e.to_dict() for e in self.evaluations]
        d["conflicts"] = [asdict(c) for c in self.conflicts]
        return d
