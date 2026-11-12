"""Typed contracts for DESK Weft nodes.

A contract is the single source of truth for one node: identity, version, typed inputs and outputs, error codes,
timeout, retry and idempotency policy, and which DESK engine it adapts. The Weft node files are generated from
these contracts (desk.weft.weftgen) and the executor enforces them at run time (desk.weft.nodes).

Weft itself has no per-node timeout, retry or version field (upstream TODO.md, nodes/metadata.md), so those
policies are enforced on the DESK side of the adapter.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# contract type -> (python check, Weft type)
_TYPES = {
    "string": (lambda v: isinstance(v, str), "String"),
    "number": (lambda v: isinstance(v, (int, float)) and not isinstance(v, bool), "Number"),
    "boolean": (lambda v: isinstance(v, bool), "Boolean"),
    "list[string]": (lambda v: isinstance(v, list) and all(isinstance(x, str) for x in v), "List[String]"),
    "object": (lambda v: isinstance(v, dict), "JsonDict"),
}

# Error contract: every failed call carries exactly one of these codes.
ERROR_CODES = {
    "INVALID_INPUT": "inputs do not satisfy the node contract",
    "UNKNOWN_NODE": "no such node",
    "NODE_UNAVAILABLE": "the node is declared but no DESK engine backs it yet",
    "PROJECT_NOT_FOUND": "the project id does not resolve to a DESK project folder",
    "RECORD_NOT_FOUND": "a referenced DESK record (requirements, profile, evidence, approval) does not exist",
    "APPROVAL_REQUIRED": "the node needs a recorded human approval that is missing, rejected or for another subject",
    "MUTATION_NOT_AUTHORIZED": "the node would change a live design and live execution is not authorized",
    "PROVIDER_UNAVAILABLE": "the model provider is not configured or did not answer",
    "PROVIDER_OUTPUT_INVALID": "the model answer failed deterministic validation",
    "TIMEOUT": "the engine did not finish inside the node's timeout",
    "ENGINE_ERROR": "the DESK engine raised",
    "UNAUTHORIZED": "missing or wrong service token",
}
RETRYABLE = {"PROVIDER_UNAVAILABLE", "TIMEOUT"}

_ID = re.compile(r"^Desk[A-Z][A-Za-z0-9]+$")
_FIELD = re.compile(r"^[a-z][A-Za-z0-9]*$")
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
RESERVED_OUTPUTS = {"passed", "blocking", "evidence"}


@dataclass(frozen=True)
class Field:
    name: str
    type: str
    description: str = ""
    required: bool = True

    @property
    def weft_type(self) -> str:
        return _TYPES[self.type][1]

    def accepts(self, value: Any) -> bool:
        return _TYPES[self.type][0](value)


@dataclass(frozen=True)
class NodeContract:
    node_id: str
    version: str
    summary: str
    engine: str                               # the DESK module/function this node adapts
    stage: str                                # requirements | components | schematic | pcb | quality | human | model
    inputs: Tuple[Field, ...] = ()
    outputs: Tuple[Field, ...] = ()
    status: str = "available"                 # available | unavailable (declared, fails closed with NODE_UNAVAILABLE)
    timeout_s: float = 30.0
    max_attempts: int = 1                     # attempts for RETRYABLE errors; deterministic engines stay at 1
    idempotency: str = "input_hash"           # input_hash: same inputs -> stored result | none: always executes
    mutation: bool = False                    # would change a live design
    requires_approval: Optional[str] = None   # approval stage that must be recorded for the same subject
    errors: Tuple[str, ...] = ("INVALID_INPUT", "PROJECT_NOT_FOUND", "ENGINE_ERROR", "TIMEOUT")
    unavailable_reason: str = ""

    @property
    def weft_file(self) -> str:
        return re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", "_", self.node_id[len("Desk"):]).lower() + ".weft"

    def problems(self) -> List[str]:
        """Static contract defects (checked by tests and at registry load)."""
        out = []
        if not _ID.match(self.node_id):
            out.append(f"{self.node_id}: id must be DeskPascalCase")
        if not re.match(r"^\d+\.\d+\.\d+$", self.version):
            out.append(f"{self.node_id}: version must be MAJOR.MINOR.PATCH")
        names = set()
        for f in self.inputs + self.outputs:
            if f.type not in _TYPES:
                out.append(f"{self.node_id}.{f.name}: unknown type {f.type}")
            if not _FIELD.match(f.name):
                out.append(f"{self.node_id}.{f.name}: field names are camelCase")
        for group, label in ((self.inputs, "input"), (self.outputs, "output")):
            seen = set()
            for f in group:
                if f.name in seen:
                    out.append(f"{self.node_id}: duplicate {label} {f.name}")
                seen.add(f.name)
            names |= seen
        if not any(f.name == "projectId" for f in self.inputs):
            out.append(f"{self.node_id}: every node takes projectId")
        for f in self.outputs:
            if f.name in RESERVED_OUTPUTS:
                out.append(f"{self.node_id}: output {f.name} is reserved by the envelope")
            if not f.required:
                out.append(f"{self.node_id}.{f.name}: outputs are always present")
        for code in self.errors:
            if code not in ERROR_CODES:
                out.append(f"{self.node_id}: unknown error code {code}")
        if self.status not in ("available", "unavailable"):
            out.append(f"{self.node_id}: bad status {self.status}")
        if self.status == "unavailable" and not self.unavailable_reason:
            out.append(f"{self.node_id}: an unavailable node says why")
        if self.max_attempts < 1 or self.timeout_s <= 0:
            out.append(f"{self.node_id}: bad timeout/retry policy")
        if self.idempotency not in ("input_hash", "none"):
            out.append(f"{self.node_id}: bad idempotency policy")
        return out

    def validate_inputs(self, payload: Any) -> List[str]:
        if not isinstance(payload, dict):
            return ["inputs must be a JSON object"]
        errs = []
        known = {f.name for f in self.inputs}
        for f in self.inputs:
            if f.name not in payload or payload[f.name] is None:
                if f.required:
                    errs.append(f"missing input '{f.name}' ({f.type})")
                continue
            if not f.accepts(payload[f.name]):
                errs.append(f"input '{f.name}' must be {f.type}")
        for k in payload:
            if k not in known:
                errs.append(f"unknown input '{k}'")
        return errs

    def validate_outputs(self, outputs: Any) -> List[str]:
        if not isinstance(outputs, dict):
            return ["outputs must be an object"]
        errs = []
        for f in self.outputs:
            if f.name not in outputs:
                errs.append(f"engine adapter did not produce output '{f.name}'")
            elif not f.accepts(outputs[f.name]):
                errs.append(f"output '{f.name}' must be {f.type}")
        for k in outputs:
            if k not in {f.name for f in self.outputs}:
                errs.append(f"undeclared output '{k}'")
        return errs

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node": self.node_id, "version": self.version, "summary": self.summary, "engine": self.engine,
            "stage": self.stage, "status": self.status, "unavailableReason": self.unavailable_reason,
            "inputs": [{"name": f.name, "type": f.type, "required": f.required, "description": f.description} for f in self.inputs],
            "outputs": [{"name": f.name, "type": f.type, "description": f.description} for f in self.outputs],
            "envelopeOutputs": ["passed: boolean", "blocking: list[string]", "evidence: list[string]"],
            "errors": list(self.errors),
            "policy": {"timeoutS": self.timeout_s, "maxAttempts": self.max_attempts, "retryOn": sorted(RETRYABLE & set(self.errors)),
                       "idempotency": self.idempotency, "mutation": self.mutation, "requiresApproval": self.requires_approval},
            "weftFile": self.weft_file,
        }


def F(name: str, type_: str, description: str = "", required: bool = True) -> Field:
    return Field(name, type_, description, required)


_PROJECT = F("projectId", "string", "DESK project id (folder name under the projects root)")
_RUN = F("runId", "string", "Weft run id, for traceability")


def _planned(node_id: str, stage: str, summary: str, engine: str, reason: str, mutation: bool = False,
             approval: Optional[str] = None) -> NodeContract:
    return NodeContract(node_id, "0.1.0", summary, engine, stage, inputs=(_PROJECT, _RUN), outputs=(),
                        status="unavailable", unavailable_reason=reason, mutation=mutation, requires_approval=approval,
                        errors=("INVALID_INPUT", "NODE_UNAVAILABLE"))


CONTRACTS: Tuple[NodeContract, ...] = (
    # ---- requirements and architecture ------------------------------------------------------------------
    NodeContract(
        "DeskRequirementIntake", "1.0.0", "Store the client requirement text as a DESK record and hand back its hash.",
        "desk.weft.store.RecordStore.put_requirements", "requirements",
        inputs=(_PROJECT, _RUN, F("requirements", "string", "client requirement text")),
        outputs=(F("requirementsHash", "string", "sha256 of the stored text; later nodes take this, not the text"),
                 F("charCount", "number")),
        errors=("INVALID_INPUT", "PROJECT_NOT_FOUND", "ENGINE_ERROR", "TIMEOUT")),
    NodeContract(
        "DeskRequirementValidator", "1.0.0", "Extract engineering features deterministically and report what is missing.",
        "desk.domain_intelligence.classifier.extract_requirements", "requirements",
        inputs=(_PROJECT, _RUN, F("requirementsHash", "string")),
        outputs=(F("featureNames", "list[string]"), F("missingInformation", "list[string]")),
        errors=("INVALID_INPUT", "PROJECT_NOT_FOUND", "RECORD_NOT_FOUND", "ENGINE_ERROR", "TIMEOUT")),
    NodeContract(
        "DeskDomainClassifier", "1.0.0", "Classify the requirements into a PCB domain archetype with overlays.",
        "desk.domain_intelligence.api.classify", "requirements",
        inputs=(_PROJECT, _RUN, F("requirementsHash", "string")),
        outputs=(F("primaryArchetype", "string", "empty when unclassified"), F("classificationStatus", "string"),
                 F("confidence", "number"), F("overlays", "list[string]"), F("missingInformation", "list[string]")),
        errors=("INVALID_INPUT", "PROJECT_NOT_FOUND", "RECORD_NOT_FOUND", "ENGINE_ERROR", "TIMEOUT")),
    NodeContract(
        "DeskDesignProfileCompiler", "1.0.0", "Compile the engineering design profile and its rule set for the classified domain.",
        "desk.domain_intelligence.profile_compiler.compile_profile", "requirements",
        inputs=(_PROJECT, _RUN, F("requirementsHash", "string")),
        outputs=(F("profileHash", "string", "DesignProfile hash; the compiled profile is stored as a DESK record"),
                 F("profileStatus", "string"), F("enforcedRuleCount", "number"), F("advisoryRuleCount", "number")),
        errors=("INVALID_INPUT", "PROJECT_NOT_FOUND", "RECORD_NOT_FOUND", "ENGINE_ERROR", "TIMEOUT")),
    NodeContract(
        "DeskComponentFamilyResolver", "1.0.0", "Resolve the component families the compiled profile requires.",
        "desk.domain_intelligence.registry.DomainLibrary.family", "requirements",
        inputs=(_PROJECT, _RUN, F("profileHash", "string")),
        outputs=(F("families", "list[string]"), F("unknownFamilies", "list[string]")),
        errors=("INVALID_INPUT", "PROJECT_NOT_FOUND", "RECORD_NOT_FOUND", "ENGINE_ERROR", "TIMEOUT")),
    _planned("DeskArchetypeMatcher", "requirements", "Match a classified design against archetype reference designs.",
             "desk.domain_intelligence", "covered today by DeskDomainClassifier candidates; no separate matcher engine"),
    # ---- power / copper ---------------------------------------------------------------------------------
    NodeContract(
        "DeskPowerDistributionAnalyzer", "1.0.0",
        "Derive minimum trace width (IPC-2221) for every current limit in the compiled profile. Values are computed, never supplied.",
        "desk.ipc.trace_width_mil", "pcb",
        inputs=(_PROJECT, _RUN, F("profileHash", "string")),
        outputs=(F("netCount", "number"), F("widestTraceMil", "number"), F("report", "object", "net -> current and width")),
        errors=("INVALID_INPUT", "PROJECT_NOT_FOUND", "RECORD_NOT_FOUND", "ENGINE_ERROR", "TIMEOUT")),
    # ---- quality ----------------------------------------------------------------------------------------
    NodeContract(
        "DeskQualityGate", "1.0.0",
        "Evaluate DESK's hard acceptance gates from recorded verification evidence. Missing or stale evidence fails closed.",
        "desk.quality.QualityGateEvaluator.evaluate", "quality",
        inputs=(_PROJECT, _RUN, F("profileHash", "string"), F("evidenceRef", "string", "name of a DESK evidence record")),
        outputs=(F("approved", "boolean"), F("totalScore", "number"), F("failures", "list[string]")),
        errors=("INVALID_INPUT", "PROJECT_NOT_FOUND", "RECORD_NOT_FOUND", "ENGINE_ERROR", "TIMEOUT")),
    NodeContract(
        "DeskReleaseGate", "1.0.0",
        "Confirm that manufacturing release is allowed: quality gate approved and a human manufacturing approval recorded for this profile.",
        "desk.weft.store.RecordStore.find_approval", "quality",
        inputs=(_PROJECT, _RUN, F("profileHash", "string"), F("evidenceRef", "string"), F("approvalRef", "string")),
        outputs=(F("releaseAllowed", "boolean"), F("approvalRef", "string")),
        requires_approval="manufacturing",
        errors=("INVALID_INPUT", "PROJECT_NOT_FOUND", "RECORD_NOT_FOUND", "APPROVAL_REQUIRED", "ENGINE_ERROR", "TIMEOUT")),
    # ---- human ------------------------------------------------------------------------------------------
    NodeContract(
        "DeskApprovalRecorder", "1.0.0",
        "Record a human decision taken in a Weft HumanQuery as a DESK approval record bound to a subject hash.",
        "desk.weft.store.RecordStore.put_approval", "human",
        inputs=(_PROJECT, _RUN, F("stage", "string", "bom | schematic | manufacturing | exception | profile"),
                F("decision", "string", "approved | rejected"), F("subjectHash", "string", "what was approved"),
                F("note", "string", "free text from the approver", required=False)),
        outputs=(F("approvalRef", "string"), F("approved", "boolean")),
        idempotency="none",
        errors=("INVALID_INPUT", "PROJECT_NOT_FOUND", "ENGINE_ERROR", "TIMEOUT")),
    # ---- model ------------------------------------------------------------------------------------------
    NodeContract(
        "DeskRequirementExtractor", "1.0.0",
        "Ask a model to restate the stored requirements as structured notes. Advisory only: the deterministic classifier decides.",
        "desk.orchestrator (provider adapters)", "model",
        inputs=(_PROJECT, _RUN, F("requirementsHash", "string")),
        outputs=(F("notesRef", "string", "DESK record holding the validated model notes"), F("provider", "string"),
                 F("model", "string")),
        timeout_s=120.0, max_attempts=2,
        errors=("INVALID_INPUT", "PROJECT_NOT_FOUND", "RECORD_NOT_FOUND", "PROVIDER_UNAVAILABLE", "PROVIDER_OUTPUT_INVALID",
                "ENGINE_ERROR", "TIMEOUT")),
    # ---- reliability (desk/reliability): diagnosis and recovery planning are deterministic and read-only ----
    NodeContract(
        "DeskFailureRecorder", "1.0.0",
        "Store a structured failure record (category, execution state, identity, evidence) and classify its signature.",
        "desk.reliability.failure_classifier.classify_record", "reliability",
        inputs=(_PROJECT, _RUN, F("category", "string", "one of desk.reliability.models.FailureCategory"),
                F("module", "string"), F("operation", "string"), F("message", "string"),
                F("executionState", "string", "desk.reliability.models.ExecutionState", required=False),
                F("documentUuid", "string", required=False), F("windowId", "string", required=False),
                F("evidence", "object", "{id-free list under 'items': [{kind, source, summary}]}", required=False)),
        outputs=(F("failureRef", "string", "DESK record name of the failure"), F("signature", "string"), F("category", "string")),
        idempotency="none",
        errors=("INVALID_INPUT", "PROJECT_NOT_FOUND", "ENGINE_ERROR", "TIMEOUT")),
    NodeContract(
        "DeskFailureDiagnoser", "1.0.0",
        "Deterministic root-cause diagnosis of a stored failure from its evidence and the project's route/journal files. "
        "Returns hypotheses with confidence; CONFIRMED only from rules, never from a model.",
        "desk.reliability.root_cause.diagnose", "reliability",
        inputs=(_PROJECT, _RUN, F("failureRef", "string")),
        outputs=(F("rootCauseCategory", "string", "empty when UNKNOWN"), F("confidence", "string"), F("statement", "string"),
                 F("knownFailures", "list[string]"), F("missingEvidence", "list[string]"), F("hypothesisCount", "number")),
        errors=("INVALID_INPUT", "PROJECT_NOT_FOUND", "RECORD_NOT_FOUND", "ENGINE_ERROR", "TIMEOUT")),
    NodeContract(
        "DeskRecoveryPlanner", "1.0.0",
        "Policy-classified recovery plan for a diagnosed failure: AUTO actions, APPROVAL actions and refused ones. "
        "Proposals only; nothing is executed through the node service.",
        "desk.reliability.recovery_planner.plan", "reliability",
        inputs=(_PROJECT, _RUN, F("failureRef", "string")),
        outputs=(F("planRef", "string"), F("actionKinds", "list[string]"), F("requiresApproval", "boolean"),
                 F("refused", "list[string]"), F("verificationCriteria", "list[string]")),
        errors=("INVALID_INPUT", "PROJECT_NOT_FOUND", "RECORD_NOT_FOUND", "ENGINE_ERROR", "TIMEOUT")),
    NodeContract(
        "DeskRoutingCheckpointStatus", "1.0.0",
        "Read the routing checkpoint of a project: best valid SES, unrouted count, chunk outcomes and the engine profile.",
        "desk.routing.checkpoint.RoutingCheckpoint", "reliability",
        inputs=(_PROJECT, _RUN),
        outputs=(F("hasBest", "boolean"), F("bestUnrouted", "number", "-1 when no checkpoint"), F("chunkOutcomes", "list[string]"),
                 F("engineVersion", "string"), F("failureCategory", "string", "empty when the last run ended without a failure")),
        idempotency="none",
        errors=("INVALID_INPUT", "PROJECT_NOT_FOUND", "ENGINE_ERROR", "TIMEOUT")),
    _planned("DeskRecoveryExecutor", "reliability", "Execute an approved recovery action against the live design.",
             "desk.reliability.recovery_executor", "live recovery runs in the DESK process with the bridge; the node service "
             "cannot verify a live mutation and therefore does not execute one", mutation=True, approval="recovery"),
    # ---- declared, not yet backed: they fail closed -----------------------------------------------------
    _planned("DeskComponentSearch", "components", "Search supplier catalogues for candidate parts.",
             "desk.component_intelligence.api.find_component", "needs supplier network access; not wired into the node service yet"),
    _planned("DeskMPNResolver", "components", "Resolve a manufacturer part number to one component identity.",
             "desk.component_intelligence.api.resolve_component_identity", "not wired into the node service yet"),
    _planned("DeskDatasheetVerifier", "components", "Verify electrical parameters against the datasheet.",
             "desk.component_intelligence.api.verify_component", "DESK stores datasheet references only; there is no datasheet parser"),
    _planned("DeskComponentVerifier", "components", "Run V1-V4 component verification.",
             "desk.component_intelligence.api.verify_component", "not wired into the node service yet"),
    _planned("DeskAlternativeFinder", "components", "Find drop-in alternatives.",
             "desk.component_intelligence.catalog.alternatives", "not wired into the node service yet"),
    _planned("DeskBOMGenerator", "components", "Generate the procurement BOM.",
             "desk.component_intelligence.api.build_procurement_bom", "not wired into the node service yet"),
    _planned("DeskBlockPlanner", "schematic", "Plan schematic blocks.", "BLOCK_PLAN.md (manual)",
             "block planning is a manual DESK step; there is no planner engine"),
    _planned("DeskPinMapValidator", "schematic", "Lint block specs: every pin mapped, QA computed.", "desk.spec.lint",
             "not wired into the node service yet"),
    _planned("DeskSchematicCompiler", "schematic", "Draw the schematic in EasyEDA.", "tools/build.py",
             "live EasyEDA mutation; needs DESK write_op, an approval record and explicit authorization", mutation=True, approval="schematic"),
    _planned("DeskERCValidator", "schematic", "Run the offline electrical rule check.", "desk.erc.check",
             "not wired into the node service yet"),
    _planned("DeskNetlistVerifier", "schematic", "Compare the drawn netlist with the block specs.", "desk.netcheck.compare",
             "reading the drawn netlist needs the live EasyEDA bridge"),
    _planned("DeskPlacementPlanner", "pcb", "Plan component placement.", "desk.placement_intel", "not wired into the node service yet"),
    _planned("DeskPlacementValidator", "pcb", "Validate placement against the profile.", "desk.placement.check",
             "not wired into the node service yet"),
    _planned("DeskRoutingPlanner", "pcb", "Produce the routing plan and net priorities.", "desk.router.RoutingPlanGenerator",
             "not wired into the node service yet"),
    _planned("DeskRoutingExecutor", "pcb", "Route the board with Freerouting and import the result.", "tools/route.py",
             "live EasyEDA mutation; needs DESK write_op, an approval record and explicit authorization", mutation=True, approval="schematic"),
    _planned("DeskCopperPlanner", "pcb", "Plan copper zones and ground planes.", "desk.copper.CopperPlaneEngine",
             "not wired into the node service yet"),
    _planned("DeskDRCAnalyzer", "quality", "Parse and diagnose DRC results.", "desk.drc_engine",
             "the DRC itself runs inside EasyEDA; DESK has no native geometric DRC"),
    _planned("DeskConnectivityVerifier", "quality", "Verify physical connectivity of every net.",
             "desk.routing.connectivity.PhysicalConnectivityVerifier", "not wired into the node service yet"),
    _planned("DeskThermalAnalyzer", "quality", "Thermal analysis.", "desk.profile.ThermalProfile",
             "DESK has an ampacity audit only; there is no thermal simulation"),
    _planned("DeskManufacturingVerifier", "quality", "Check BOM, pick-and-place and Gerber consistency.", "desk.release",
             "not wired into the node service yet"),
    _planned("DeskReleaseGenerator", "quality", "Export and package the manufacturing release.", "tools/release.py",
             "export needs the live EasyEDA bridge", mutation=False, approval="manufacturing"),
)

BY_ID: Dict[str, NodeContract] = {c.node_id: c for c in CONTRACTS}


def get(node_id: str) -> Optional[NodeContract]:
    return BY_ID.get(node_id)


def all_problems() -> List[str]:
    out: List[str] = []
    for c in CONTRACTS:
        out.extend(c.problems())
    if len(BY_ID) != len(CONTRACTS):
        out.append("duplicate node id")
    files = [c.weft_file for c in CONTRACTS]
    if len(set(files)) != len(files):
        out.append("two nodes map to the same .weft file")
    return out
