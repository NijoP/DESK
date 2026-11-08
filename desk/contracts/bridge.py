"""Language-Independent Data Contracts: ECAD Bridge & IPC Protocol.
Version: 1.0.0
Authoritative Schema for Python and TypeScript/JavaScript interchange.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class BridgeRequest:
    request_id: str
    code: str
    window_id: Optional[str] = None
    timeout_ms: int = 5000
    is_mutation: bool = False
    expected_doc_uuid: Optional[str] = None


@dataclass
class BridgeResponse:
    request_id: str
    success: bool
    result: Optional[Any] = None
    error: Optional[str] = None
    execution_time_ms: float = 0.0


@dataclass
class DocumentInfoContract:
    uuid: str
    name: str
    doc_type: str  # "pcb", "schematic"
    window_id: str
    is_active: bool
