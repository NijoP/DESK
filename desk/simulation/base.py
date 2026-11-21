"""Simulator abstraction: the engine-neutral data model and the interface every simulation engine implements.

An engine (ngspice today; others later) receives a `Circuit` (desk.simulation.netlist) and returns a
`SimulationResult`. Nothing here imports or launches an engine, so `import desk.simulation` costs nothing
when no simulator is installed.
"""
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

# Printed by every CLI report and stored in every result, verification report and export.
SAFETY_NOTICE = ("Simulation alone does not prove a PCB is electrically or thermally safe. Combine it with "
                 "hand calculations, datasheet verification and independent engineering checks. "
                 "Software-tested with fixtures; not validated on a live design.")

# Run status
COMPLETED, FAILED = "COMPLETED", "FAILED"

# Diagnostic categories (error classification for failed or degraded runs)
ENGINE_NOT_FOUND = "ENGINE_NOT_FOUND"          # simulator executable not installed / not configured
TIMEOUT = "TIMEOUT"                            # run exceeded its wall-clock budget and was killed
NETLIST_ERROR = "NETLIST_ERROR"                # the engine rejected or ignored a netlist line
MODEL_ERROR = "MODEL_ERROR"                    # a referenced device model is missing or invalid
CONVERGENCE = "CONVERGENCE"                    # an analysis aborted (timestep too small, no convergence)
CONVERGENCE_ASSISTED = "CONVERGENCE_ASSISTED"  # converged only through gmin/source stepping fallbacks
MEASURE_FAILED = "MEASURE_FAILED"              # a requested measurement could not be evaluated
OUTPUT_TOO_LARGE = "OUTPUT_TOO_LARGE"          # result file exceeded the configured size bound
NO_OUTPUT = "NO_OUTPUT"                        # an analysis produced no result data
ENGINE_CRASH = "ENGINE_CRASH"                  # non-zero exit the log does not explain
UNKNOWN = "UNKNOWN"

ERROR, WARNING = "error", "warning"


@dataclass
class Diagnostic:
    category: str
    severity: str
    message: str
    analysis: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Measurement:
    name: str
    value: Optional[float]
    analysis: Optional[str] = None
    ok: bool = True
    detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AnalysisResult:
    """One analysis' data: `scale` names the independent vector (time, frequency) or is None for OP."""
    id: str
    type: str
    status: str
    scale: Optional[str] = None
    vectors: Dict[str, List[Any]] = field(default_factory=dict)   # complex values for AC
    points: int = 0

    def to_dict(self) -> Dict[str, Any]:
        def enc(v):
            return [v.real, v.imag] if isinstance(v, complex) else v
        return {"id": self.id, "type": self.type, "status": self.status, "scale": self.scale,
                "points": self.points, "vectors": {k: [enc(x) for x in vs] for k, vs in self.vectors.items()}}


@dataclass
class SimulationResult:
    engine: str
    status: str
    engine_version: str = ""
    analyses: Dict[str, AnalysisResult] = field(default_factory=dict)
    measurements: Dict[str, Measurement] = field(default_factory=dict)
    diagnostics: List[Diagnostic] = field(default_factory=list)
    models: List[Dict[str, Any]] = field(default_factory=list)      # provenance of every model card used
    excluded: List[Dict[str, str]] = field(default_factory=list)    # parts excluded on purpose, with reason
    elapsed_s: float = 0.0
    log_tail: str = ""
    notice: str = SAFETY_NOTICE

    @property
    def errors(self) -> List[Diagnostic]:
        return [d for d in self.diagnostics if d.severity == ERROR]

    def to_dict(self) -> Dict[str, Any]:
        return {"engine": self.engine, "engine_version": self.engine_version, "status": self.status,
                "elapsed_s": self.elapsed_s, "notice": self.notice,
                "diagnostics": [d.to_dict() for d in self.diagnostics],
                "measurements": {k: m.to_dict() for k, m in self.measurements.items()},
                "models": self.models, "excluded": self.excluded,
                "analyses": {k: a.to_dict() for k, a in self.analyses.items()},
                "log_tail": self.log_tail}


@dataclass
class EngineInfo:
    name: str
    available: bool
    version: str = ""
    path: str = ""
    detail: str = ""


class Simulator:
    """Interface for a simulation engine. Implementations must be safe to construct when the engine is absent."""
    name = "abstract"

    def probe(self) -> EngineInfo:
        raise NotImplementedError

    def run(self, circuit, timeout_s: Optional[float] = None, work_dir: Optional[str] = None) -> SimulationResult:
        raise NotImplementedError


# ---- registry ---------------------------------------------------------------------------------
# name -> "module:Class" (imported only when requested) or a zero-argument factory.
_REGISTRY: Dict[str, Any] = {"ngspice": "desk.simulation.ngspice:NgspiceSimulator"}


def register(name: str, factory) -> None:
    """Register an engine: `factory` is a zero-argument callable or a lazy "module:Class" string."""
    _REGISTRY[name] = factory


def names() -> List[str]:
    return sorted(_REGISTRY)


def get(name: str) -> Simulator:
    from desk.errors import UsageError
    if name not in _REGISTRY:
        raise UsageError(f"unknown simulation engine '{name}' (known: {', '.join(names())})")
    f = _REGISTRY[name]
    if isinstance(f, str):
        import importlib
        mod, cls = f.split(":")
        f = getattr(importlib.import_module(mod), cls)
    return f()


def engines() -> List[EngineInfo]:
    out = []
    for n in names():
        try:
            info = get(n).probe()
            info.name = n          # the registry name is what users pass to --engine
            out.append(info)
        except Exception as e:  # a broken adapter must not hide the others
            out.append(EngineInfo(n, False, detail=f"probe error: {str(e)[:120]}"))
    return out
