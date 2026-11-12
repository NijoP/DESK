"""Routing checkpoint: the best valid SES survives every later failure.

The checkpoint directory (projects/<P>/state/route/checkpoint/) holds `chunk_best.ses` and `checkpoint.json`. A new SES
is accepted only after it has been validated (parses, carries routes) and only when it is at least as good as the
current best (fewer unrouted connections, or equal unrouted with more copper). Acceptance writes a temporary file
and renames it, so a crash during the copy cannot truncate `best.ses`. Nothing in this module ever deletes the
best SES; a failed chunk leaves it untouched (UPS_1000 F-012 / ROUTING_BLOCKERS "chunked execution throws away all
work").

Zero external dependencies.
"""
from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class SESValidation:
    valid: bool
    tracks: int = 0
    vias: int = 0
    nets: int = 0
    size_bytes: int = 0
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def validate_ses(path: str) -> SESValidation:
    """A SES is valid when it exists, is non-empty, parses as an S-expression and carries at least one routed wire
    or via inside (routes (network_out ...)). A truncated file (JVM killed while writing) fails here."""
    if not path or not os.path.exists(path):
        return SESValidation(False, reason="missing")
    size = os.path.getsize(path)
    if size == 0:
        return SESValidation(False, size_bytes=0, reason="empty")
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        return SESValidation(False, size_bytes=size, reason=f"unreadable: {e}")
    if text.count("(") != text.count(")"):
        return SESValidation(False, size_bytes=size, reason="unbalanced parentheses (truncated file)")
    try:
        from desk.routing.connectivity import SESParser
        tracks, vias = SESParser.parse_ses_copper(text)
    except Exception as e:
        return SESValidation(False, size_bytes=size, reason=f"parse error: {e}")
    nets = len({t["net"] for t in tracks} | {v["net"] for v in vias})
    if not tracks and not vias:
        return SESValidation(False, size_bytes=size, reason="no routed wires or vias in (routes (network_out ...))")
    return SESValidation(True, tracks=len(tracks), vias=len(vias), nets=nets, size_bytes=size)


@dataclass
class CheckpointState:
    best_ses: Optional[str] = None
    best_unrouted: Optional[int] = None
    best_tracks: int = 0
    best_vias: int = 0
    best_from_chunk: Optional[int] = None
    observed_best_unrouted: Optional[int] = None     # best count seen in any pass, SES or not
    chunks: List[Dict[str, Any]] = field(default_factory=list)
    rejected: List[Dict[str, Any]] = field(default_factory=list)
    dsn_sha256: str = ""
    engine_version: str = ""
    updated: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RoutingCheckpoint:
    """Owner of `best.ses`. Resume with `resume_input()`; offer candidates with `offer()`."""

    def __init__(self, directory: str, dsn_sha256: str = "", engine_version: str = ""):
        self.dir = directory
        os.makedirs(self.dir, exist_ok=True)
        self.best_path = os.path.join(self.dir, "chunk_best.ses")
        self.manifest = os.path.join(self.dir, "checkpoint.json")
        self.state = self._load()
        if dsn_sha256 and self.state.dsn_sha256 and self.state.dsn_sha256 != dsn_sha256:
            # The board changed since the checkpoint was written: keep the file as evidence, start a fresh best.
            self._archive("dsn-changed")
            self.state = CheckpointState()
        if dsn_sha256:
            self.state.dsn_sha256 = dsn_sha256
        if engine_version:
            self.state.engine_version = engine_version
        self._save()

    # ---- persistence ------------------------------------------------------------------------------------
    def _load(self) -> CheckpointState:
        try:
            with open(self.manifest, encoding="utf-8") as f:
                d = json.load(f)
            st = CheckpointState(**{k: v for k, v in d.items() if k in CheckpointState.__dataclass_fields__})
            if st.best_ses and not os.path.exists(st.best_ses):
                st.best_ses, st.best_unrouted = None, None
            return st
        except Exception:
            return CheckpointState()

    def _save(self) -> None:
        self.state.updated = time.time()
        tmp = self.manifest + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.state.to_dict(), f, indent=1)
        os.replace(tmp, self.manifest)

    def _archive(self, why: str) -> None:
        if os.path.exists(self.best_path):
            try:
                shutil.copyfile(self.best_path, os.path.join(self.dir, f"best_{why}_{int(time.time())}.ses"))
            except OSError:
                pass

    # ---- API --------------------------------------------------------------------------------------------
    @property
    def best_unrouted(self) -> Optional[int]:
        return self.state.best_unrouted

    def has_best(self) -> bool:
        return bool(self.state.best_ses) and os.path.exists(self.best_path) and os.path.getsize(self.best_path) > 0

    def resume_input(self) -> Optional[str]:
        """Path of the SES the next chunk continues from, or None."""
        return self.best_path if self.has_best() else None

    def observe_pass(self, unrouted: Optional[int]) -> None:
        if unrouted is None:
            return
        if self.state.observed_best_unrouted is None or unrouted < self.state.observed_best_unrouted:
            self.state.observed_best_unrouted = int(unrouted)
            self._save()

    def offer(self, ses_path: str, unrouted: Optional[int], chunk: int, meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Validate a candidate and adopt it as best when it is an improvement. Returns {"accepted", "reason", ...}.
        The current best is never removed, whatever the candidate looks like."""
        v = validate_ses(ses_path)
        rec: Dict[str, Any] = {"chunk": chunk, "ses": ses_path, "unrouted": unrouted, "validation": v.to_dict(), "ts": time.time(),
                               **(meta or {})}
        if not v.valid:
            rec["accepted"], rec["reason"] = False, f"invalid SES: {v.reason}"
            self.state.rejected.append(rec)
            self.state.chunks.append(rec)
            self._save()
            return rec
        if unrouted is None:
            rec["accepted"], rec["reason"] = False, "unrouted count unknown: cannot rank against the checkpoint"
            self.state.rejected.append(rec)
            self.state.chunks.append(rec)
            self._save()
            return rec
        better = (self.state.best_unrouted is None or unrouted < self.state.best_unrouted
                  or (unrouted == self.state.best_unrouted and v.tracks + v.vias > self.state.best_tracks + self.state.best_vias))
        if not better:
            rec["accepted"], rec["reason"] = False, f"not better than checkpoint ({self.state.best_unrouted} unrouted)"
            self.state.chunks.append(rec)
            self._save()
            return rec
        tmp = self.best_path + ".tmp"
        shutil.copyfile(ses_path, tmp)
        os.replace(tmp, self.best_path)
        self.state.best_ses = self.best_path
        self.state.best_unrouted = int(unrouted)
        self.state.best_tracks, self.state.best_vias = v.tracks, v.vias
        self.state.best_from_chunk = chunk
        self.observe_pass(unrouted)
        rec["accepted"], rec["reason"] = True, "new best"
        self.state.chunks.append(rec)
        self._save()
        return rec

    def export(self, dest: str) -> bool:
        """Copy best.ses to `dest` (atomic). False when there is no best."""
        if not self.has_best():
            return False
        tmp = dest + ".tmp"
        shutil.copyfile(self.best_path, tmp)
        os.replace(tmp, dest)
        return True

    def summary(self) -> Dict[str, Any]:
        d = self.state.to_dict()
        d["has_best"] = self.has_best()
        return d
