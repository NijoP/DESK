"""Per-version capability profiles of the Freerouting engines DESK can drive.

Every Freerouting version behaves differently on this host and the differences decide whether a bounded, resumable
run is even possible. A profile states what has been MEASURED for a version; fields that have not been measured
say so (`verified=False`) and the planner treats them conservatively. Nothing here is inferred from a version
number alone: the evidence column names the incident or live test that measured the behaviour.

    honours_max_passes     the engine stops after `-mp N` / router.max_passes and writes its SES
    honours_job_timeout    the engine stops at router.job_timeout and writes its SES
    writes_ses_on_stop     a graceful stop (SIGINT) makes it write the SES (never on Windows: no SIGINT for a child JVM)
    config_style           "legacy_global": only %TEMP%/freerouting/freerouting.json is read (2.1.x)
                           "per_run": freerouting.json in the CWD and --router.* flags (2.2+)
    stagnation_flag        --router.autorouter.stagnation_pass_limit accepted
    continuation           `-de board.dsn+previous.ses` continues from routed copper
    java_min               minimum Java major version (class-file 69 = Java 25 for 2.2+)
    probe_blocks_online    `--help` blocks on the online version check after printing its banner (UPS_1000 F-007)

Zero external dependencies.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Dict, Optional, Sequence, Tuple


@dataclass(frozen=True)
class EngineProfile:
    name: str
    version_prefix: Tuple[int, ...]
    honours_max_passes: Optional[bool]        # None = not measured
    honours_job_timeout: Optional[bool]
    writes_ses_on_stop: Optional[bool]
    config_style: str
    stagnation_flag: Optional[bool]
    continuation: Optional[bool]
    java_min: int
    probe_blocks_online: bool = False
    verified: bool = False
    evidence: Sequence[str] = ()
    notes: Sequence[str] = ()

    @property
    def boundable(self) -> Optional[bool]:
        """Can a chunk end by itself with a SES? True/False when measured, None when unknown."""
        if self.honours_max_passes is None and self.honours_job_timeout is None:
            return None
        return bool(self.honours_max_passes or self.honours_job_timeout)

    def can_stop_gracefully(self, platform: str = os.name) -> bool:
        return bool(self.writes_ses_on_stop) and platform != "nt"

    def to_dict(self) -> Dict[str, object]:
        return {"name": self.name, "version_prefix": list(self.version_prefix), "honours_max_passes": self.honours_max_passes,
                "honours_job_timeout": self.honours_job_timeout, "writes_ses_on_stop": self.writes_ses_on_stop,
                "config_style": self.config_style, "stagnation_flag": self.stagnation_flag, "continuation": self.continuation,
                "java_min": self.java_min, "probe_blocks_online": self.probe_blocks_online, "verified": self.verified,
                "boundable": self.boundable, "evidence": list(self.evidence), "notes": list(self.notes)}


PROFILES: Tuple[EngineProfile, ...] = (
    EngineProfile(
        "freerouting-2.1", (2, 1), honours_max_passes=False, honours_job_timeout=False, writes_ses_on_stop=False,
        config_style="legacy_global", stagnation_flag=False, continuation=True, java_min=17, probe_blocks_online=True,
        verified=True,
        evidence=("KF-20261111-006", "INC-20261112-009", "UPS_1000 F-007", "UPS_1000 attempts 5 and 6"),
        notes=("ignores -mp, router.max_passes and job_timeout on this host; SES written only when 100 % routed",
               "terminate() on Windows loses the board; a chunked run cannot be bounded with this engine",
               "prints its banner in ~2 s then blocks on the online version check for > 60 s")),
    EngineProfile(
        "freerouting-2.5", (2, 5), honours_max_passes=True, honours_job_timeout=None, writes_ses_on_stop=None,
        config_style="per_run", stagnation_flag=False, continuation=True, java_min=25, verified=True,
        evidence=("INC-20261112-009 (JDK 25, max_passes honoured, SES written)", "docs/engineering/DENSE_BOARD_BENCHMARK_REPORT.md"),
        notes=("rejects --router.autorouter.stagnation_pass_limit (\"No field found\")", "needs Java 25 (class file 69)")),
    EngineProfile(
        "freerouting-2.4", (2, 4), honours_max_passes=None, honours_job_timeout=None, writes_ses_on_stop=None,
        config_style="per_run", stagnation_flag=None, continuation=True, java_min=25, verified=False,
        evidence=("KF-20261111-006 (needs Java 25)",), notes=("pass/timeout behaviour not measured on this host",)),
    EngineProfile(
        "freerouting-2.2", (2, 2), honours_max_passes=None, honours_job_timeout=None, writes_ses_on_stop=None,
        config_style="per_run", stagnation_flag=None, continuation=True, java_min=25, verified=False,
        evidence=("KF-20261111-006 (needs Java 25)",), notes=("pass/timeout behaviour not measured on this host",)),
    EngineProfile(
        "freerouting-2.0", (2, 0), honours_max_passes=None, honours_job_timeout=None, writes_ses_on_stop=None,
        config_style="legacy_global", stagnation_flag=False, continuation=None, java_min=17, verified=False,
        evidence=(), notes=("never exercised by DESK",)),
)

UNKNOWN = EngineProfile("unknown", (), honours_max_passes=None, honours_job_timeout=None, writes_ses_on_stop=None,
                        config_style="per_run", stagnation_flag=None, continuation=None, java_min=17, verified=False,
                        notes=("no profile for this version; chunk behaviour is measured on the first chunk",))


def version_tuple(ver: str) -> Tuple[int, ...]:
    nums = re.findall(r"\d+", ver or "")
    return tuple(int(n) for n in nums[:3]) if nums else ()


def profile_for(version: str) -> EngineProfile:
    """Longest matching version prefix wins; unknown versions get the conservative UNKNOWN profile."""
    vt = version_tuple(version)
    best: Optional[EngineProfile] = None
    for p in PROFILES:
        if vt[:len(p.version_prefix)] == p.version_prefix and (best is None or len(p.version_prefix) > len(best.version_prefix)):
            best = p
    return best or UNKNOWN


def java_major(version_text: str) -> Optional[int]:
    """Parse `java -version` output ("openjdk version \"25\" ..." or "1.8.0_292") into a major number."""
    m = re.search(r'version "(\d+)(?:\.(\d+))?', version_text or "")
    if not m:
        return None
    major = int(m.group(1))
    if major == 1 and m.group(2):
        return int(m.group(2))
    return major
