"""JLCPCB Manufacturing Capabilities Declaration."""

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class JLCPCBCapabilities:
    supports_pcb_quote: bool = True
    supports_pcba_quote: bool = True
    supports_smt_assembly: bool = True
    supports_stencil: bool = True
    min_trace_width_mil: float = 3.5
    min_spacing_mil: float = 3.5
    min_drill_mm: float = 0.2
    max_layers: int = 32
    supported_surface_finishes: tuple = ("HASL", "LeadFree HASL", "ENIG", "Hard Gold")
    supported_colors: tuple = ("Green", "Blue", "Red", "Yellow", "White", "Black", "Purple")
    extended_part_fee_usd: float = 3.00  # Feeder changeover cost per extended line
    setup_fee_pcba_usd: float = 8.00     # Base PCBA setup cost
