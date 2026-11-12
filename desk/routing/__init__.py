"""DESK Routing Intelligence V2 Subsystem.
Autonomous PCB Routing Optimization, Engineering Maturity,
Execution-Speed Improvement, and Zero-New-Violation Verification.

Lazy facade (T-19): `import desk.routing` costs about a millisecond. A submodule is imported
the first time one of its names is read (`desk.routing.DSNTree`), so a tool that only needs
the DSN parser never pays for the orchestrator, connectivity or recovery engines.
Every public name below is still importable with `from desk.routing import X`.
"""
import importlib

# name -> submodule (no `typing` import here: it alone costs ~20 ms in a fresh interpreter)
_EXPORTS = {
    # board
    "BoardIntelligenceEngine": "board", "BoardPad": "board", "BoardTrack": "board", "BoardVia": "board",
    "BoardKeepout": "board", "SpatialHashIndex": "board",
    # escape / priority / congestion / strategy
    "PadEscapeEngine": "escape", "PadEscapeAnalysis": "escape",
    "AdaptivePriorityEngine": "priority", "NetPriorityScore": "priority",
    "CongestionMap": "congestion", "CongestionCell": "congestion",
    "RoutingStrategyEngine": "strategy", "NetStrategyAssignment": "strategy",
    # engine orchestration
    "RoutingEngineOrchestrator": "orchestrator", "EngineExecutionResult": "orchestrator",
    # dsn
    "DSNTree": "dsn", "SExprParser": "dsn", "DSNInvariantViolationError": "dsn",
    # width
    "TraceWidthManager": "width", "WidthWideningPlan": "width", "WideningCandidate": "width",
    # connectivity
    "PhysicalConnectivityVerifier": "connectivity", "BoardConnectivityResult": "connectivity",
    "NetConnectivityReport": "connectivity",
    # quality
    "DRCAcceptanceEngine": "quality", "DRCComparisonResult": "quality", "DRCViolationRecord": "quality",
    # recovery
    "IntelligentRecoveryEngine": "recovery", "SelectiveRecoveryPlan": "recovery", "RoutingFailureDiagnostic": "recovery",
    # profiling
    "RoutingProfiler": "profiling", "RoutingExecutionProfile": "profiling", "PhaseTimingRecord": "profiling",
    # modes
    "RoutingModeManager": "modes", "RoutingExecutionModeConfig": "modes",
    "FAST_MODE": "modes", "BALANCED_MODE": "modes", "PRECISION_MODE": "modes",
}

__all__ = list(_EXPORTS)


def __getattr__(name: str):
    mod = _EXPORTS.get(name)
    if mod is None:
        raise AttributeError(f"module 'desk.routing' has no attribute {name!r}")
    value = getattr(importlib.import_module(f"desk.routing.{mod}"), name)
    globals()[name] = value          # cache: the second access is a plain attribute read
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))
