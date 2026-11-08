"""JLCPCB Manufacturing Integration Subsystem."""

from .capabilities import JLCPCBCapabilities
from .pcba_catalog import (
    JLCPCBPCBACatalog,
    PartAssemblyType,
    AssemblyComponentInfo,
    ROTATION_OFFSET_TABLE,
)
from .quote import (
    JLCPCBQuotingEngine,
    ManufacturingQuote,
    PCBQuoteItem,
    PCBAQuoteItem,
    DFMValidationResult,
)
from .order_guard import (
    OrderApprovalManager,
    OrderExecutionBlockedError,
    get_order_guard,
)
from .client import JLCPCBClient

__all__ = [
    "JLCPCBCapabilities",
    "JLCPCBPCBACatalog",
    "PartAssemblyType",
    "AssemblyComponentInfo",
    "ROTATION_OFFSET_TABLE",
    "JLCPCBQuotingEngine",
    "ManufacturingQuote",
    "PCBQuoteItem",
    "PCBAQuoteItem",
    "DFMValidationResult",
    "OrderApprovalManager",
    "OrderExecutionBlockedError",
    "get_order_guard",
    "JLCPCBClient",
]
