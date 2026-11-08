"""Data contracts for the Mental-Model Framework and Compiled Policies.
Zero external dependencies.
"""
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any, Optional

@dataclass
class MentalModel:
    model_id: str                      # e.g. "M1_SCHEMATIC", "M2_PLACEMENT"
    version: str                       # e.g. "1.0.0"
    domain: str                        # "schematic", "placement", "routing", "copper", "mfg", "verification"
    applicability_conditions: List[str]
    required_context: List[str]
    decision_hierarchy: List[str]
    hard_constraints: Dict[str, Any]
    trade_off_priorities: List[str]
    exceptions: List[Dict[str, Any]] = field(default_factory=list)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    verification_requirements: List[str] = field(default_factory=list)
    evidence_sources: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class CompiledPolicy:
    policy_id: str                     # e.g. "M2_PLACEMENT_WATCH_a3b2c1"
    model_id: str
    task_type: str
    version: str
    profile_hash: str
    compact_rules: List[str]           # Task-specific, high-density instructions
    hard_constraints: Dict[str, Any]
    output_schema: Dict[str, Any]
    verification_checklist: List[str]
    token_estimate: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_compact_prompt(self) -> str:
        """Format as a compact token-efficient instruction block for an AI agent."""
        lines = [
            f"=== POLICY [{self.model_id}:{self.task_type}] v{self.version} (profile {self.profile_hash[:8]}) ===",
            "HARD CONSTRAINTS:"
        ]
        for k, v in self.hard_constraints.items():
            lines.append(f"- {k}: {v}")
        lines.append("TASK RULES:")
        for r in self.compact_rules:
            lines.append(f"- {r}")
        lines.append("VERIFICATION CHECKLIST:")
        for chk in self.verification_checklist:
            lines.append(f"[ ] {chk}")
        return "\n".join(lines)
