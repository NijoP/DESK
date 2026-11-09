"""Subsystem Twelve: Fast but Safe Routing Execution Modes.
Defines FAST, BALANCED, and PRECISION configurations.
Controls computation strategy, pass budgets, and heuristics without relaxing
any physical, electrical, or DRC manufacturing acceptance criteria.
Zero external dependencies.
"""
from __future__ import annotations
from typing import Dict, Any, Optional
from dataclasses import dataclass


@dataclass(frozen=True)
class RoutingExecutionModeConfig:
    """Configuration parameters for a routing execution mode."""
    mode_name: str
    max_passes: int
    timeout_sec: float
    stagnation_patience: int
    grid_wire_mil: float
    grid_via_mil: float
    run_congestion_analysis: bool
    corridor_reservation_enabled: bool
    recovery_max_attempts: int
    allow_drc_waivers: bool = False  # NEVER True in any mode!
    mandatory_connectivity_check: bool = True  # Always True in all modes!


FAST_MODE = RoutingExecutionModeConfig(
    mode_name="FAST",
    max_passes=12,
    timeout_sec=120.0,
    stagnation_patience=4,
    grid_wire_mil=1.25,
    grid_via_mil=1.25,
    run_congestion_analysis=False,
    corridor_reservation_enabled=False,
    recovery_max_attempts=2
)

BALANCED_MODE = RoutingExecutionModeConfig(
    mode_name="BALANCED",
    max_passes=30,
    timeout_sec=300.0,
    stagnation_patience=6,
    grid_wire_mil=1.25,
    grid_via_mil=1.25,
    run_congestion_analysis=True,
    corridor_reservation_enabled=True,
    recovery_max_attempts=4
)

PRECISION_MODE = RoutingExecutionModeConfig(
    mode_name="PRECISION",
    max_passes=60,
    timeout_sec=600.0,
    stagnation_patience=10,
    grid_wire_mil=1.25,
    grid_via_mil=1.25,
    run_congestion_analysis=True,
    corridor_reservation_enabled=True,
    recovery_max_attempts=6
)


class RoutingModeManager:
    """Manages mode selection and ensures invariant safety across modes."""

    MODES: Dict[str, RoutingExecutionModeConfig] = {
        "FAST": FAST_MODE,
        "BALANCED": BALANCED_MODE,
        "PRECISION": PRECISION_MODE
    }

    @classmethod
    def get_mode(cls, mode_name: str) -> RoutingExecutionModeConfig:
        clean = (mode_name or "BALANCED").upper().strip()
        if clean not in cls.MODES:
            return BALANCED_MODE
        return cls.MODES[clean]
