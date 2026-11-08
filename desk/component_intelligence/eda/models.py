"""
EDA Asset Models for Symbols, Footprints, and Devices.
Completely decoupled from commercial supplier offerings.
"""

from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class AssetType(str, enum.Enum):
    SYMBOL = "SYMBOL"
    FOOTPRINT = "FOOTPRINT"
    DEVICE = "DEVICE"
    MODEL_3D = "MODEL_3D"


@dataclass
class EDAAsset:
    """Represents a CAD library asset (symbol, footprint, 3D model)."""
    asset_id: str
    canonical_desk_id: str
    provider_id: str               # "easyeda", "kicad", "local"
    asset_type: AssetType
    asset_name: str
    pin_count: int = 0
    pins: List[Dict[str, str]] = field(default_factory=list)  # [{"num": "1", "name": "VCC"}]
    content_hash: str = ""
    raw_data: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "canonical_desk_id": self.canonical_desk_id,
            "provider_id": self.provider_id,
            "asset_type": self.asset_type.value,
            "asset_name": self.asset_name,
            "pin_count": self.pin_count,
            "pins": self.pins,
            "content_hash": self.content_hash,
            "created_at": self.created_at,
        }
