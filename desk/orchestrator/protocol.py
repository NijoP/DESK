"""Common Worker Protocol for DESK Multi-Model Orchestration.
Defines standardized data contracts for tasks, results, and provider health.
Zero external dependencies.
"""
import time
import json
import uuid
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any

@dataclass
class TaskRequest:
    task_id: str = field(default_factory=lambda: f"TASK_{uuid.uuid4().hex[:8]}")
    task_type: str = "general"             # "schematic", "placement", "routing", "drc_diagnosis", "fast_reasoning"
    prompt: str = ""
    system_prompt: Optional[str] = None
    output_schema: Optional[Dict[str, Any]] = None
    execution_level: int = 1               # 0=Deterministic, 1=Fast, 2=Capable+Validated, 3=Dual-Review, 4=Frontier
    timeout_sec: Optional[float] = None    # None = router applies the per-tier default (see router.tier_timeout)
    preferred_provider: Optional[str] = None # "agy", "pi", or None (auto)
    preferred_model: Optional[str] = None
    thinking_level: Optional[str] = None   # "off" | "low" | "medium" | "high"; None = router applies tier default
    requires_vision: bool = False          # task includes an image (board screenshot); router picks a vision model
    images: List[str] = field(default_factory=list)  # image file paths or data:/http(s): URLs sent as image_url parts
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskRequest":
        return cls(**data)

@dataclass
class TaskResult:
    task_id: str
    success: bool
    provider: str                          # "agy", "pi", "deterministic"
    model: str
    output_text: str
    output_json: Optional[Dict[str, Any]] = None
    latency_ms: float = 0.0
    execution_level: int = 1
    error: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskResult":
        return cls(**data)

@dataclass
class ProviderHealth:
    provider_name: str                     # "agy", "pi"
    available: bool
    cli_path: str
    supported_models: List[str] = field(default_factory=list)
    last_checked: float = 0.0
    status_message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
