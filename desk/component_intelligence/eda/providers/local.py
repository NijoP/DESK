"""
Local Offline EDA Asset Provider.
Indexes local JSON device and pin definitions from library/devices.json and library/pins/
allowing offline symbol and footprint resolution with zero network or bridge dependencies.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Dict, List, Optional

from desk.component_intelligence.eda.base import EDALibraryProvider
from desk.component_intelligence.eda.capabilities import EDACapabilities
from desk.component_intelligence.eda.models import AssetType, EDAAsset


class LocalEDALibraryProvider(EDALibraryProvider):
    """Provides symbols and footprints from DESK's offline local library."""

    def __init__(self, library_dir: Optional[str | Path] = None) -> None:
        caps = EDACapabilities(symbols=True, footprints=True, devices=True, models_3d=False)
        super().__init__(provider_id="local", name="DESK Local Library", capabilities=caps)

        if library_dir is None:
            repo_root = Path(__file__).resolve().parent.parent.parent.parent.parent
            self.library_dir = repo_root / "library"
        else:
            self.library_dir = Path(library_dir)

        self._devices_cache: Dict[str, Dict] = {}
        self._pins_cache: Dict[str, List[Dict[str, str]]] = {}
        self._load_local_data()

    def _load_local_data(self) -> None:
        devices_file = self.library_dir / "devices.json"
        if devices_file.is_file():
            try:
                with open(devices_file, "r", encoding="utf-8") as f:
                    self._devices_cache = json.load(f)
            except Exception:
                self._devices_cache = {}

        pins_dir = self.library_dir / "pins"
        if pins_dir.is_dir():
            for pfile in pins_dir.glob("*.json"):
                try:
                    mpn = pfile.stem
                    with open(pfile, "r", encoding="utf-8") as f:
                        self._pins_cache[mpn] = json.load(f)
                except Exception:
                    pass

    def search_symbols(self, query: str) -> List[EDAAsset]:
        q_upper = query.strip().upper()
        assets: List[EDAAsset] = []
        for mpn, pins in self._pins_cache.items():
            if q_upper in mpn.upper():
                asset_id = f"sym_local_{mpn}"
                h = hashlib.sha256(json.dumps(pins, sort_keys=True).encode()).hexdigest()[:16]
                assets.append(
                    EDAAsset(
                        asset_id=asset_id,
                        canonical_desk_id="",
                        provider_id=self.provider_id,
                        asset_type=AssetType.SYMBOL,
                        asset_name=f"Symbol for {mpn}",
                        pin_count=len(pins),
                        pins=pins,
                        content_hash=h,
                    )
                )
        return assets

    def search_footprints(self, query: str) -> List[EDAAsset]:
        q_upper = query.strip().upper()
        assets: List[EDAAsset] = []
        seen_footprints = set()
        for mpn, dev in self._devices_cache.items():
            fp = dev.get("footprint", "").strip()
            if fp and q_upper in fp.upper() and fp not in seen_footprints:
                seen_footprints.add(fp)
                asset_id = f"fp_local_{fp}"
                assets.append(
                    EDAAsset(
                        asset_id=asset_id,
                        canonical_desk_id="",
                        provider_id=self.provider_id,
                        asset_type=AssetType.FOOTPRINT,
                        asset_name=fp,
                        raw_data=dev,
                    )
                )
        return assets

    def get_asset(self, asset_id: str) -> Optional[EDAAsset]:
        if asset_id.startswith("sym_local_"):
            mpn = asset_id.replace("sym_local_", "")
            pins = self._pins_cache.get(mpn)
            if pins is not None:
                h = hashlib.sha256(json.dumps(pins, sort_keys=True).encode()).hexdigest()[:16]
                return EDAAsset(
                    asset_id=asset_id,
                    canonical_desk_id="",
                    provider_id=self.provider_id,
                    asset_type=AssetType.SYMBOL,
                    asset_name=f"Symbol for {mpn}",
                    pin_count=len(pins),
                    pins=pins,
                    content_hash=h,
                )
        return None
