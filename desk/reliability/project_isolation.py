"""Project identity and window binding for concurrent EasyEDA Pro work.

The authoritative identity of a live target is the project's verified uuid and the document uuid DESK is bound to,
never the active window, the most recently opened window, a cached window id, a terminal variable or a window
title. Window ids are per gateway connection and rotate on every reconnect (UPS_1000 F-002, INC-20261112-013).

`SessionResolver` discovers the windows a gateway reports, asks each one which project and document it hosts, and
binds only when exactly one window matches. Ambiguity (two windows with the same project, none) is a refusal
(`IdentityUnverified`), never a guess. `verify_target()` is the invariant every live mutation must prove right
before and right after it runs:

    EXPECTED DOCUMENT UUID == ACTUAL ACTIVE DOCUMENT UUID in the bound window

The gateway is injected (`GatewayClient`) so the whole module is unit-testable with three fake windows, rotating
ids and a gateway restart; `desk.bridge` supplies the real HTTP client.

Zero external dependencies.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Dict, List, Optional, Protocol, Sequence, Tuple

from desk.errors import IdentityUnverified, BridgeWindowRotated
from desk.reliability.models import HealthStatus, new_id

PROJECT_INFO_JS = ("const p=await eda.dmt_Project.getCurrentProjectInfo();"
                   "const d=await eda.dmt_SelectControl.getCurrentDocumentInfo();"
                   "return {project_uuid:p&&p.uuid, project_name:p&&(p.friendlyName||p.name), "
                   "document_uuid:d&&d.uuid, document_type:d&&(d.docType||d.type)};")
ACTIVE_DOC_JS = "const d=await eda.dmt_SelectControl.getCurrentDocumentInfo(); return d?d.uuid:null;"

_DISCONNECTED_RX = re.compile(r"(no longer connected|not connected|unknown window|window .* not found|disconnected)", re.I)


def is_window_disconnected_error(text: str) -> bool:
    """True when a gateway error text says the bound window id is gone (ids rotate on reconnect)."""
    return bool(text) and bool(_DISCONNECTED_RX.search(str(text)))


class GatewayClient(Protocol):
    """The two calls the resolver needs. `execute` returns the raw gateway envelope {"success", "result", "error"}."""
    def windows(self) -> List[Dict[str, Any]]: ...
    def execute(self, window_id: Optional[str], code: str, timeout: float = 5.0) -> Dict[str, Any]: ...


@dataclass
class WindowIdentity:
    window_id: str
    project_uuid: Optional[str] = None
    project_name: Optional[str] = None
    document_uuid: Optional[str] = None
    document_type: Optional[str] = None
    reachable: bool = True
    error: str = ""


@dataclass
class ProjectSession:
    """Independent identity of one project's live binding (one per project, never shared across projects)."""
    project_id: str
    project_path: str
    project_uuid: str = ""
    schematic_uuid: str = ""
    pcb_uuid: str = ""
    gateway_endpoint: str = ""
    window_id: Optional[str] = None
    window_generation: int = 0        # bumps every time the window id changes
    session_generation: int = 0       # bumps on every (re)bind
    last_verified_at: float = 0.0
    health_status: HealthStatus = HealthStatus.UNVERIFIED
    session_id: str = field(default_factory=lambda: new_id("SES"))
    bound_document_uuid: str = ""     # the document the last verify_target proved active
    last_window_id: Optional[str] = None   # the id before the last invalidate(), for the rotation note
    notes: List[str] = field(default_factory=list)

    @property
    def bound(self) -> bool:
        return bool(self.window_id) and self.health_status in (HealthStatus.HEALTHY, HealthStatus.DEGRADED)

    def documents(self) -> Tuple[str, ...]:
        return tuple(u for u in (self.pcb_uuid, self.schematic_uuid) if u)

    def invalidate(self, reason: str) -> None:
        self.notes.append(f"{time.strftime('%H:%M:%S')} invalidated: {reason}")
        self.health_status = HealthStatus.DISCONNECTED
        if self.window_id:
            self.last_window_id = self.window_id
        self.window_id = None
        self.bound_document_uuid = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["health_status"] = self.health_status.value
        d["bound"] = self.bound
        return d


class SessionResolver:
    """Binds a `ProjectSession` to the one gateway window that hosts its project/document; refuses otherwise."""

    def __init__(self, gateway: GatewayClient, now: Callable[[], float] = time.time, probe_timeout: float = 5.0):
        self.gateway = gateway
        self.now = now
        self.probe_timeout = probe_timeout

    # ---- discovery ------------------------------------------------------------------------------------------
    def discover(self) -> List[WindowIdentity]:
        """Ask every connected window which project and document it hosts. Never raises on a single bad window."""
        out: List[WindowIdentity] = []
        try:
            wins = self.gateway.windows()
        except Exception as e:  # gateway down: no windows, caller decides
            return [WindowIdentity(window_id="", reachable=False, error=f"gateway unreachable: {e}")]
        for w in wins:
            wid = str(w.get("windowId") or w.get("id") or "")
            if not wid:
                continue
            ident = WindowIdentity(window_id=wid)
            try:
                resp = self.gateway.execute(wid, PROJECT_INFO_JS, timeout=self.probe_timeout)
                if resp.get("success") and isinstance(resp.get("result"), dict):
                    r = resp["result"]
                    ident.project_uuid = r.get("project_uuid") or None
                    ident.project_name = r.get("project_name") or None
                    ident.document_uuid = r.get("document_uuid") or None
                    ident.document_type = r.get("document_type") or None
                else:
                    ident.reachable = False
                    ident.error = str(resp.get("error") or "no result")
            except Exception as e:
                ident.reachable = False
                ident.error = str(e)
            out.append(ident)
        return out

    @staticmethod
    def matches(ident: WindowIdentity, project_uuid: str, documents: Sequence[str]) -> bool:
        """A window matches when it hosts the project uuid; when the project uuid is unknown, when its active
        document is one of the bound documents. A name is never enough (two projects can share one)."""
        if not ident.reachable:
            return False
        if project_uuid:
            return ident.project_uuid == project_uuid
        return bool(ident.document_uuid) and ident.document_uuid in tuple(documents)

    # ---- binding --------------------------------------------------------------------------------------------
    def resolve(self, session: ProjectSession, windows: Optional[List[WindowIdentity]] = None) -> ProjectSession:
        """Bind `session` to the unique matching window or raise IdentityUnverified. The old window id is kept
        only when it still matches; a changed id bumps `window_generation`."""
        if not session.project_uuid and not session.documents():
            raise IdentityUnverified(
                f"STOP: project '{session.project_id}' has neither project_uuid nor document uuids in project.json; "
                "DESK cannot prove which EasyEDA window is yours. Run tools/ping.py in the right window and bind it.",
                project_id=session.project_id)
        wins = windows if windows is not None else self.discover()
        if wins and not wins[0].window_id and not wins[0].reachable:
            session.health_status = HealthStatus.DISCONNECTED
            raise IdentityUnverified(f"STOP: {wins[0].error}", project_id=session.project_id)
        hits = [w for w in wins if self.matches(w, session.project_uuid, session.documents())]
        if len(hits) != 1:
            session.health_status = HealthStatus.DISCONNECTED if not hits else HealthStatus.UNVERIFIED
            seen = ", ".join(f"{w.window_id}:{w.project_name or '?'}" for w in wins if w.window_id) or "none"
            raise IdentityUnverified(
                f"STOP: {len(hits)} EasyEDA window(s) host project '{session.project_id}' "
                f"(uuid {session.project_uuid or 'unknown'}; windows seen: {seen}). Binding needs exactly one match; "
                "no mutation is allowed until the identity is unambiguous.",
                project_id=session.project_id, candidates=[w.window_id for w in hits])
        win = hits[0]
        if session.window_id != win.window_id:
            old = session.window_id or session.last_window_id
            if old and old != win.window_id:
                session.notes.append(f"window id rotated {old} -> {win.window_id}")
            session.window_id = win.window_id
            session.window_generation += 1
        if not session.project_uuid and win.project_uuid:
            session.project_uuid = win.project_uuid
        session.session_generation += 1
        session.health_status = HealthStatus.HEALTHY
        session.last_verified_at = self.now()
        session.bound_document_uuid = win.document_uuid or ""
        return session

    def verify_target(self, session: ProjectSession, expected_document_uuid: str) -> bool:
        """The mutation invariant: the bound window's ACTIVE document is the expected one. Never opens a document."""
        if not session.window_id:
            session.health_status = HealthStatus.UNVERIFIED
            return False
        try:
            resp = self.gateway.execute(session.window_id, ACTIVE_DOC_JS, timeout=self.probe_timeout)
        except Exception as e:
            session.notes.append(f"verify_target error: {e}")
            session.health_status = HealthStatus.DEGRADED
            return False
        if not resp.get("success"):
            err = str(resp.get("error") or "")
            if is_window_disconnected_error(err):
                session.invalidate(err)
                raise BridgeWindowRotated(f"window {session.window_id or '?'} is no longer connected: {err}",
                                          project_id=session.project_id)
            session.health_status = HealthStatus.DEGRADED
            return False
        ok = resp.get("result") == expected_document_uuid
        session.last_verified_at = self.now()
        session.bound_document_uuid = str(resp.get("result") or "")
        session.health_status = HealthStatus.HEALTHY if ok else HealthStatus.UNVERIFIED
        return ok

    def rebind_after_rotation(self, session: ProjectSession, reason: str = "rotation") -> ProjectSession:
        """Invalidate the stale id and resolve again by identity. Raises IdentityUnverified when ambiguous."""
        session.invalidate(reason)
        return self.resolve(session)


def session_from_project(project_path: str, project_info: Dict[str, Any], endpoint: str = "") -> ProjectSession:
    """Build a ProjectSession from a loaded project.json (fields: name, project_uuid, sheet_uuid, pcb_uuid, window_id)."""
    import os
    return ProjectSession(
        project_id=str(project_info.get("name") or os.path.basename(project_path.rstrip("/\\")) or "unknown"),
        project_path=project_path,
        project_uuid=str(project_info.get("project_uuid") or ""),
        schematic_uuid=str(project_info.get("sheet_uuid") or ""),
        pcb_uuid=str(project_info.get("pcb_uuid") or ""),
        gateway_endpoint=endpoint,
        window_id=project_info.get("window_id") or None,
    )
