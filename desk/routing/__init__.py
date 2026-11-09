"""DESK Routing Intelligence V2 Subsystem.
Autonomous PCB Routing Optimization, Engineering Maturity,
Execution-Speed Improvement, and Zero-New-Violation Verification.
"""
from desk.routing.board import (
    BoardIntelligenceEngine,
    BoardPad,
    BoardTrack,
    BoardVia,
    BoardKeepout,
    SpatialHashIndex,
)
from desk.routing.escape import (
    PadEscapeEngine,
    PadEscapeAnalysis,
)
from desk.routing.priority import (
    AdaptivePriorityEngine,
    NetPriorityScore,
)
from desk.routing.congestion import (
    CongestionMap,
    CongestionCell,
)
from desk.routing.strategy import (
    RoutingStrategyEngine,
    NetStrategyAssignment,
)
from desk.routing.orchestrator import (
    RoutingEngineOrchestrator,
    EngineExecutionResult,
)
from desk.routing.dsn import (
    DSNTree,
    SExprParser,
    DSNInvariantViolationError,
)
from desk.routing.width import (
    TraceWidthManager,
    WidthWideningPlan,
    WideningCandidate,
)
from desk.routing.connectivity import (
    PhysicalConnectivityVerifier,
    BoardConnectivityResult,
    NetConnectivityReport,
)
from desk.routing.quality import (
    DRCAcceptanceEngine,
    DRCComparisonResult,
    DRCViolationRecord,
)
from desk.routing.recovery import (
    IntelligentRecoveryEngine,
    SelectiveRecoveryPlan,
    RoutingFailureDiagnostic,
)
from desk.routing.profiling import (
    RoutingProfiler,
    RoutingExecutionProfile,
    PhaseTimingRecord,
)
from desk.routing.modes import (
    RoutingModeManager,
    RoutingExecutionModeConfig,
    FAST_MODE,
    BALANCED_MODE,
    PRECISION_MODE,
)

__all__ = [
    "BoardIntelligenceEngine",
    "BoardPad",
    "BoardTrack",
    "BoardVia",
    "BoardKeepout",
    "SpatialHashIndex",
    "PadEscapeEngine",
    "PadEscapeAnalysis",
    "AdaptivePriorityEngine",
    "NetPriorityScore",
    "CongestionMap",
    "CongestionCell",
    "RoutingStrategyEngine",
    "NetStrategyAssignment",
    "RoutingEngineOrchestrator",
    "EngineExecutionResult",
    "DSNTree",
    "SExprParser",
    "DSNInvariantViolationError",
    "TraceWidthManager",
    "WidthWideningPlan",
    "WideningCandidate",
    "PhysicalConnectivityVerifier",
    "BoardConnectivityResult",
    "NetConnectivityReport",
    "DRCAcceptanceEngine",
    "DRCComparisonResult",
    "DRCViolationRecord",
    "IntelligentRecoveryEngine",
    "SelectiveRecoveryPlan",
    "RoutingFailureDiagnostic",
    "RoutingProfiler",
    "RoutingExecutionProfile",
    "PhaseTimingRecord",
    "RoutingModeManager",
    "RoutingExecutionModeConfig",
    "FAST_MODE",
    "BALANCED_MODE",
    "PRECISION_MODE",
]
