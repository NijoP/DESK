"""DESK reliability layer: observe, collect evidence, classify, diagnose, plan, gate, recover, read back, verify, learn.

Modules
    models              typed failure / evidence / recovery records and the 30 failure categories
    project_isolation   ProjectSession, SessionResolver (window binding by project/document uuid, rotation handling)
    api_registry        version-aware EasyEDA API capability registry and per-method verification contracts
    mutation            MutationContract: precondition -> journal -> identity -> execute -> readback -> postcondition
    retry_policy        bounded retries with backoff/jitter gated on execution state
    circuit_breaker     per-service breakers
    failure_classifier  exceptions / engine results / log text -> category + execution state
    registry            known-failure signatures (from incidents and the UPS_1000 live test)
    evidence            deterministic evidence collector (layer 1)
    root_cause          deterministic diagnosis (layer 2) and evidence-grounded model packets (layer 3)
    recovery_policy     AUTO / APPROVAL / REFUSE risk classes and attempt limits
    recovery_planner    category + evidence -> policy-classified plan
    recovery_executor   runs handlers, verifies independently, journals
    health_monitor      per-project component health
    resource_monitor    budgets, RSS sampling, child-process registry
    learning            incidents, recovery outcomes, known-failure promotion
    supervisor          the lifecycle
"""
from desk.reliability.models import (FailureCategory, ExecutionState, Confidence, RiskClass, HealthStatus, FailureRecord,
                                     EvidenceRef, Hypothesis, RecoveryAction, RecoveryPlan, RecoveryOutcome, VerificationResult,
                                     fingerprint, redact)

__all__ = ["FailureCategory", "ExecutionState", "Confidence", "RiskClass", "HealthStatus", "FailureRecord", "EvidenceRef",
           "Hypothesis", "RecoveryAction", "RecoveryPlan", "RecoveryOutcome", "VerificationResult", "fingerprint", "redact"]
