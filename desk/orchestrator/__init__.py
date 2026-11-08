"""DESK Multi-Model Orchestration and Capability Routing Subsystem.
Integrates AGY CLI, Pi Agent, and deterministic handlers into a unified task protocol.
"""
from desk.orchestrator.protocol import TaskRequest, TaskResult, ProviderHealth
from desk.orchestrator.agy_adapter import AGYAdapter
from desk.orchestrator.pi_adapter import PiAdapter
from desk.orchestrator.router import CapabilityRouter, ProviderRegistry

__all__ = [
    "TaskRequest",
    "TaskResult",
    "ProviderHealth",
    "AGYAdapter",
    "PiAdapter",
    "CapabilityRouter",
    "ProviderRegistry"
]
