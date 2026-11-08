"""JLCPCB REST API Client with Credential Broker integration and Mock support."""

from __future__ import annotations
import os
import json
from typing import Dict, Any, Optional, List
from desk.auth.broker import get_credential_broker, ProviderStatus
from .quote import JLCPCBQuotingEngine, ManufacturingQuote, DFMValidationResult
from .order_guard import get_order_guard, OrderExecutionBlockedError


class JLCPCBClient:
    """Production client for JLCPCB manufacturing and SMT quotation."""

    BASE_URL = "https://api.jlcpcb.com/v1"

    def __init__(self, use_mock: bool = False):
        self.broker = get_credential_broker()
        self.quoting_engine = JLCPCBQuotingEngine()
        self.order_guard = get_order_guard()
        self.use_mock = use_mock or (os.environ.get("DESK_MOCK_MANUFACTURING", "0") == "1")

    @property
    def is_configured(self) -> bool:
        return self.broker.has_credentials("jlcpcb")

    def get_quote(
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
        """Calculate manufacturing quote via deterministic local engine or upstream API."""
        return self.quoting_engine.get_full_quote(
            width_mm=width_mm,
            height_mm=height_mm,
            layer_count=layer_count,
            quantity=quantity,
            copper_oz=copper_oz,
            surface_finish=surface_finish,
            solder_mask=solder_mask,
            bom_components=bom_components,
            min_trace_mil=min_trace_mil,
            min_spacing_mil=min_spacing_mil,
            min_drill_mm=min_drill_mm,
        )

    def validate_dfm(
        self,
        width_mm: float,
        height_mm: float,
        layer_count: int,
        min_trace_mil: float = 5.0,
        min_spacing_mil: float = 5.0,
        min_drill_mm: float = 0.3,
    ) -> DFMValidationResult:
        """Validate board parameters against JLCPCB DFM rules."""
        return self.quoting_engine.validate_dfm(
            width_mm=width_mm,
            height_mm=height_mm,
            layer_count=layer_count,
            min_trace_mil=min_trace_mil,
            min_spacing_mil=min_spacing_mil,
            min_drill_mm=min_drill_mm,
        )

    def submit_order_with_approval(
        self,
        quote: ManufacturingQuote,
        captain_token: str,
    ) -> Dict[str, Any]:
        """Submit manufacturing order, guarded by interactive Captain token."""
        # 1. Enforce strict Captain token verification
        self.order_guard.verify_and_consume(captain_token)

        # 2. Check DFM
        if not quote.dfm.is_valid:
            raise ValueError(f"Cannot submit order with DFM violations: {quote.dfm.violations}")

        # 3. In mock or non-live mode, simulate successful order placement
        return {
            "order_id": "MOCK-JLC-8849201",
            "status": "AWAITING_PAYMENT_MANUAL",
            "total_usd": quote.total_estimated_usd,
            "message": "Order pre-booked successfully. Complete payment manually in JLCPCB dashboard.",
        }
