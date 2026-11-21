"""Engineering sign-off records for insulation assessments.

No DESK output may call an insulation design compliant on the strength of a calculation. A compliance statement needs
all of:

    1. an EngineeringSignoff record naming the reviewer, role, date (YYYY-MM-DD), the dataset id and the
       assessment digest it reviewed (InsulationAssessment.digest(): inputs + both results + dataset id),
    2. the digest and dataset id matching the assessment being reported (any change of input or data voids it),
    3. both the clearance and the creepage result being VERIFIED-AGAINST-TABLE.

Otherwise the statement is NOT_A_COMPLIANCE_CLAIM (or says why the sign-off does not apply).

Record format (JSON):

    {"signoff_id": "INS-SO-0001", "reviewer": "<name>", "role": "<role>", "date": "2026-11-21",
     "assessment_digest": "<sha256 hex>", "dataset_id": "<dataset id>", "scope": "<what was reviewed>"}

Zero external dependencies.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, fields
from typing import Any, Dict, Optional, Tuple

from desk.errors import InsulationDataInvalid

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class EngineeringSignoff:
    signoff_id: str
    reviewer: str
    role: str
    date: str
    assessment_digest: str
    dataset_id: str
    scope: str

    def __post_init__(self):
        for f in fields(self):
            v = getattr(self, f.name)
            if not isinstance(v, str) or not v.strip():
                raise InsulationDataInvalid(f"STOP: engineering sign-off field '{f.name}' is empty",
                                            field=f.name, category="INSULATION_SIGNOFF_INVALID")
        if not _DATE.match(self.date):
            raise InsulationDataInvalid(f"STOP: engineering sign-off date must be YYYY-MM-DD, got {self.date!r}",
                                        field="date", category="INSULATION_SIGNOFF_INVALID")

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "EngineeringSignoff":
        known = {f.name for f in fields(cls)}
        unknown = sorted(set(d) - known)
        missing = sorted(known - set(d))
        if unknown or missing:
            raise InsulationDataInvalid(f"STOP: engineering sign-off record: unknown {unknown}, missing {missing}",
                                        category="INSULATION_SIGNOFF_INVALID")
        return cls(**{k: d[k] for k in known})

    @classmethod
    def load(cls, path: str) -> "EngineeringSignoff":
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            raise InsulationDataInvalid(f"STOP: engineering sign-off {path} cannot be read: {e}", path=path,
                                        category="INSULATION_SIGNOFF_INVALID")
        if not isinstance(data, dict):
            raise InsulationDataInvalid(f"STOP: engineering sign-off {path} must be a JSON object", path=path,
                                        category="INSULATION_SIGNOFF_INVALID")
        return cls.from_dict(data)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def evaluate_signoff(assessment: Any, signoff: Optional[EngineeringSignoff]) -> Tuple[bool, str]:
    """(compliance_may_be_stated, statement)."""
    from desk.insulation.engine import NOT_A_COMPLIANCE_CLAIM, Status
    if signoff is None:
        return False, NOT_A_COMPLIANCE_CLAIM
    if not isinstance(signoff, EngineeringSignoff):
        raise TypeError("signoff must be an EngineeringSignoff record")
    if signoff.assessment_digest != assessment.digest() or signoff.dataset_id != assessment.dataset_id:
        return False, (f"{NOT_A_COMPLIANCE_CLAIM} Sign-off {signoff.signoff_id} reviewed a different assessment "
                       f"(digest or dataset changed since the review).")
    statuses = (assessment.clearance.status, assessment.creepage.status)
    if any(s != Status.VERIFIED_AGAINST_TABLE for s in statuses):
        return False, (f"{NOT_A_COMPLIANCE_CLAIM} Sign-off {signoff.signoff_id} is recorded, but clearance is "
                       f"{statuses[0].value} and creepage is {statuses[1].value}; both must be VERIFIED-AGAINST-TABLE.")
    return True, (f"Engineering sign-off {signoff.signoff_id} ({signoff.reviewer}, {signoff.role}, {signoff.date}) "
                  f"records this assessment as compliant with {assessment.standard} for the stated inputs and "
                  f"assumptions; scope: {signoff.scope}.")
