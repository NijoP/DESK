"""Language-Independent Data Contracts: PCB Routing & Net Connectivity.
Version: 1.0.0
Authoritative Schema for Python and Rust router interchange.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any, Optional


@dataclass
class NetEndpointContract:
    ref: str
    pad_num: str
    net: str
    x_mm: float
    y_mm: float
    layer: int
    is_smd: bool = True


@dataclass
class TrackSegmentContract:
    net: str
    layer: int
    start_x_mm: float
    start_y_mm: float
    end_x_mm: float
    end_y_mm: float
    width_mil: float


@dataclass
class ViaContract:
    net: str
    x_mm: float
    y_mm: float
    diameter_mil: float
    drill_mil: float
    from_layer: int
    to_layer: int


@dataclass
class RoutedNetContract:
    net: str
    tracks: List[TrackSegmentContract] = field(default_factory=list)
    vias: List[ViaContract] = field(default_factory=list)
    total_length_mm: float = 0.0
    is_fully_connected: bool = False
