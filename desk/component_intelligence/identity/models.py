"""
Canonical Component Identity Models for DESK.
Enforces the fundamental architectural principle:
DESK owns canonical component identity and engineering intelligence;
external suppliers and EDA tools are secondary commercial/asset providers.
"""

from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class LifecycleStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    NRND = "NRND"  # Not Recommended for New Designs
    EOL = "EOL"    # End of Life
    OBSOLETE = "OBSOLETE"
    UNKNOWN = "UNKNOWN"


class IdentityVerificationStatus(str, enum.Enum):
    VERIFIED = "VERIFIED"
    PROVISIONAL = "PROVISIONAL"
    UNVERIFIED = "UNVERIFIED"
    CONFLICT = "CONFLICT"


@dataclass
class Manufacturer:
    """Represents a component manufacturer with controlled naming aliases."""
    id: str
    name: str
    aliases: List[str] = field(default_factory=list)
    homepage_url: Optional[str] = None
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "aliases": self.aliases,
            "homepage_url": self.homepage_url,
            "created_at": self.created_at,
        }


@dataclass
class DatasheetReference:
    """Reference to an authoritative manufacturer datasheet."""
    id: str
    url: str
    title: str = ""
    revision: Optional[str] = None
    sha256: Optional[str] = None
    local_path: Optional[str] = None
    last_checked_ts: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "url": self.url,
            "title": self.title,
            "revision": self.revision,
            "sha256": self.sha256,
            "local_path": self.local_path,
            "last_checked_ts": self.last_checked_ts,
        }


@dataclass
class CanonicalComponent:
    """
    Supplier-independent, canonical component identity record owned by DESK.
    """
    desk_id: str
    manufacturer_name: str
    normalized_manufacturer: str
    mpn: str
    normalized_mpn: str
    category: str
    description: str
    package: str
    datasheets: List[DatasheetReference] = field(default_factory=list)
    lifecycle_status: LifecycleStatus = LifecycleStatus.UNKNOWN
    verification_status: IdentityVerificationStatus = IdentityVerificationStatus.UNVERIFIED
    provenance: str = "local"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    attributes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "desk_id": self.desk_id,
            "manufacturer_name": self.manufacturer_name,
            "normalized_manufacturer": self.normalized_manufacturer,
            "mpn": self.mpn,
            "normalized_mpn": self.normalized_mpn,
            "category": self.category,
            "description": self.description,
            "package": self.package,
            "datasheets": [d.to_dict() for d in self.datasheets],
            "lifecycle_status": self.lifecycle_status.value,
            "verification_status": self.verification_status.value,
            "provenance": self.provenance,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "attributes": self.attributes,
        }
