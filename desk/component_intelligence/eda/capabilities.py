"""
EDA Provider Capabilities Declaration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class EDACapabilities:
    """Explicit capabilities supported by an EDA library provider."""
    symbols: bool = True
    footprints: bool = True
    devices: bool = True
    models_3d: bool = False
    export_kicad: bool = False
    export_easyeda: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbols": self.symbols,
            "footprints": self.footprints,
            "devices": self.devices,
            "models_3d": self.models_3d,
            "export_kicad": self.export_kicad,
            "export_easyeda": self.export_easyeda,
        }
