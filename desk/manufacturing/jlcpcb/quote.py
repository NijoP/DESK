"""JLCPCB PCB & PCBA Quote and DFM Verification Engine.

Calculates realistic manufacturing estimates and verifies DFM constraints:
- PCB fabrication pricing based on board area, layer count, surface finish, and quantity.
- PCBA SMT pricing based on setup fees, basic vs. extended feeder lines, and solder joints.
- Strict DFM rule enforcement.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from .capabilities import JLCPCBCapabilities
from .pcba_catalog import JLCPCBPCBACatalog, PartAssemblyType


@dataclass
class DFMValidationResult:
    is_valid: bool
    violations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class PCBQuoteItem:
    width_mm: float
    height_mm: float
    layer_count: int
    quantity: int
    copper_oz: int = 1
    surface_finish: str = "HASL"
    solder_mask: str = "Green"
    estimated_usd: float = 0.0


@dataclass
class PCBAQuoteItem:
    board_count: int
    total_components_per_board: int
    unique_parts_count: int
    basic_parts_count: int
    extended_parts_count: int
    setup_fee_usd: float = 8.00
    feeder_fees_usd: float = 0.0
    solder_joint_fees_usd: float = 0.0
    estimated_usd: float = 0.0


@dataclass
class ManufacturingQuote:
    pcb: PCBQuoteItem
    pcba: Optional[PCBAQuoteItem] = None
    dfm: DFMValidationResult = field(default_factory=lambda: DFMValidationResult(True))
    total_estimated_usd: float = 0.0
    currency: str = "USD"


class JLCPCBQuotingEngine:
    """Computes PCB and PCBA manufacturing quotations and runs DFM verification."""

    def __init__(self, caps: Optional[JLCPCBCapabilities] = None):
        self.caps = caps or JLCPCBCapabilities()

    def validate_dfm(
        self,
        width_mm: float,
        height_mm: float,
        layer_count: int,
        min_trace_mil: float = 5.0,
        min_spacing_mil: float = 5.0,
        min_drill_mm: float = 0.3,
    ) -> DFMValidationResult:
        """Verify DFM parameters against JLCPCB manufacturing limits."""
        violations = []
        warnings = []

        if width_mm <= 0 or height_mm <= 0:
            violations.append(f"Invalid board dimensions: {width_mm}x{height_mm} mm.")
        if width_mm > 500 or height_mm > 500:
            violations.append(f"Board dimensions ({width_mm}x{height_mm} mm) exceed maximum 500x500 mm limit.")

        if layer_count not in (1, 2, 4, 6, 8, 10, 12, 14, 16):
            violations.append(f"Unsupported layer count: {layer_count}. Supported: 1, 2, 4, 6, 8, 10, 12, 14, 16.")

        if min_trace_mil < self.caps.min_trace_width_mil:
            violations.append(
                f"Minimum trace width {min_trace_mil} mil is below JLCPCB limit of {self.caps.min_trace_width_mil} mil."
            )
        elif min_trace_mil < 4.0:
            warnings.append(f"Trace width {min_trace_mil} mil is near lower threshold (3.5 mil); standard is 5.0 mil.")

        if min_spacing_mil < self.caps.min_spacing_mil:
            violations.append(
                f"Minimum spacing {min_spacing_mil} mil is below JLCPCB limit of {self.caps.min_spacing_mil} mil."
            )

        if min_drill_mm < self.caps.min_drill_mm:
            violations.append(
                f"Minimum drill size {min_drill_mm} mm is below JLCPCB limit of {self.caps.min_drill_mm} mm."
            )

        return DFMValidationResult(is_valid=(len(violations) == 0), violations=violations, warnings=warnings)

    def calculate_pcb_quote(
        self,
        width_mm: float,
        height_mm: float,
        layer_count: int = 2,
        quantity: int = 5,
        copper_oz: int = 1,
        surface_finish: str = "HASL",
        solder_mask: str = "Green",
    ) -> PCBQuoteItem:
        """Calculate estimated PCB fabrication price."""
        # Standard special offers: $2 for 5 boards <= 100x100mm 2-layer HASL
        is_standard_size = (width_mm <= 100.0 and height_mm <= 100.0)
        
        if layer_count <= 2:
            base_price = 2.00 if (is_standard_size and quantity <= 5) else 5.00
        elif layer_count == 4:
            base_price = 12.00 if (is_standard_size and quantity <= 5) else 20.00
        elif layer_count == 6:
            base_price = 35.00
        else:
            base_price = 60.00 + (layer_count - 8) * 15.00

        # Area scaling for larger boards
        area_dm2 = (width_mm * height_mm) / 10000.0
        if area_dm2 > 1.0:
            area_multiplier = area_dm2
            base_price *= area_multiplier

        # Quantity scaling
        if quantity > 5:
            base_price += (quantity - 5) * (base_price / 5.0) * 0.4

        # Finish premium
        if surface_finish.upper() == "ENIG":
            base_price += 18.00
        elif surface_finish.upper() == "LEADFREE HASL":
            base_price += 2.00

        # Copper thickness premium
        if copper_oz == 2:
            base_price += 15.00

        return PCBQuoteItem(
            width_mm=width_mm,
            height_mm=height_mm,
            layer_count=layer_count,
            quantity=quantity,
            copper_oz=copper_oz,
            surface_finish=surface_finish,
            solder_mask=solder_mask,
            estimated_usd=round(base_price, 2),
        )

    def calculate_pcba_quote(
        self,
        board_count: int,
        bom_components: List[Dict[str, Any]],
    ) -> PCBAQuoteItem:
        """Calculate estimated PCBA SMT assembly price."""
        setup_fee = self.caps.setup_fee_pcba_usd

        unique_parts = {}
        total_joints_per_board = 0

        for item in bom_components:
            pn = item.get("lcsc_pn", "")
            pkg = item.get("package", "")
            qty = item.get("quantity", 1)
            joints = item.get("joints", 2)
            total_joints_per_board += qty * joints

            if pn not in unique_parts:
                unique_parts[pn] = JLCPCBPCBACatalog.classify_part(pn, pkg)

        extended_parts_count = sum(
            1 for p in unique_parts.values() if p.part_type == PartAssemblyType.EXTENDED
        )
        basic_parts_count = len(unique_parts) - extended_parts_count

        feeder_fees = extended_parts_count * self.caps.extended_part_fee_usd
        # Joint cost: ~$0.0017 per joint across all boards
        solder_joint_fees = round(board_count * total_joints_per_board * 0.0017, 2)

        total_pcba = setup_fee + feeder_fees + solder_joint_fees

        return PCBAQuoteItem(
            board_count=board_count,
            total_components_per_board=sum(item.get("quantity", 1) for item in bom_components),
            unique_parts_count=len(unique_parts),
            basic_parts_count=basic_parts_count,
            extended_parts_count=extended_parts_count,
            setup_fee_usd=setup_fee,
            feeder_fees_usd=feeder_fees,
            solder_joint_fees_usd=solder_joint_fees,
            estimated_usd=round(total_pcba, 2),
        )

    def get_full_quote(
        self,
        width_mm: float,
        height_mm: float,
        layer_count: int = 2,
        quantity: int = 5,
        copper_oz: int = 1,
        surface_finish: str = "HASL",
        solder_mask: str = "Green",
        bom_components: Optional[List[Dict[str, Any]]] = None,
        min_trace_mil: float = 5.0,
        min_spacing_mil: float = 5.0,
        min_drill_mm: float = 0.3,
    ) -> ManufacturingQuote:
        """Produce full itemized PCB + PCBA quotation with DFM validation."""
        dfm = self.validate_dfm(
            width_mm=width_mm,
            height_mm=height_mm,
            layer_count=layer_count,
            min_trace_mil=min_trace_mil,
            min_spacing_mil=min_spacing_mil,
            min_drill_mm=min_drill_mm,
        )

        pcb_item = self.calculate_pcb_quote(
            width_mm=width_mm,
            height_mm=height_mm,
            layer_count=layer_count,
            quantity=quantity,
            copper_oz=copper_oz,
            surface_finish=surface_finish,
            solder_mask=solder_mask,
        )

        pcba_item = None
        total = pcb_item.estimated_usd

        if bom_components is not None:
            pcba_item = self.calculate_pcba_quote(board_count=quantity, bom_components=bom_components)
            total += pcba_item.estimated_usd

        return ManufacturingQuote(
            pcb=pcb_item,
            pcba=pcba_item,
            dfm=dfm,
            total_estimated_usd=round(total, 2),
            currency="USD",
        )
