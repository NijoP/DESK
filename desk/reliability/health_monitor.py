"""Health of the subsystems one project depends on, kept separate per project.

A failed routing engine must not take the bridge or another project's session down with it, so health is reported
per component (gateway port, project window binding, journal, engine, breakers) and the overall status is the worst
component for THIS project only. Probes are injectable; the default ones are cheap (a socket probe, a file read).
Zero external dependencies.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from desk.reliability.models import HealthStatus


@dataclass
class ComponentHealth:
    name: str
    status: HealthStatus
    detail: str = ""
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "status": self.status.value, "detail": self.detail, "ts": self.ts}


_ORDER = [HealthStatus.HEALTHY, HealthStatus.UNVERIFIED, HealthStatus.DEGRADED, HealthStatus.DISCONNECTED]


class HealthMonitor:
    def __init__(self, project_path: Optional[str] = None, session: Optional[Any] = None, port_probe: Optional[Callable[[int], bool]] = None,
                 gateway: Optional[Any] = None, now: Callable[[], float] = time.time):
        self.project_path = project_path
        self.session = session
        self.gateway = gateway
        self.now = now
        self.port_probe = port_probe or self._default_port_probe
        self.history: List[Dict[str, Any]] = []

    @staticmethod
    def _default_port_probe(port: int) -> bool:
        from desk.bridge import SessionRegistry
        return SessionRegistry._probe_single_port(port, timeout=0.05)

    def gateway_health(self, port: int) -> ComponentHealth:
        from desk.reliability.circuit_breaker import BreakerRegistry
        b = BreakerRegistry.snapshot().get(f"gateway:{port}")
        if b and b.get("state") == "OPEN":
            return ComponentHealth("gateway", HealthStatus.DISCONNECTED, f"circuit open after {b.get('failures')} failures: {b.get('last_error')}")
        if self.port_probe(port):
            return ComponentHealth("gateway", HealthStatus.HEALTHY, f"port {port} accepts connections")
        return ComponentHealth("gateway", HealthStatus.DISCONNECTED, f"port {port} refused")

    def binding_health(self) -> ComponentHealth:
        s = self.session
        if s is None:
            return ComponentHealth("binding", HealthStatus.UNVERIFIED, "no session")
        wid = getattr(s, "window_id", None)
        if not wid:
            return ComponentHealth("binding", HealthStatus.DISCONNECTED, "session has no window binding")
        if self.gateway is not None:
            try:
                from desk.reliability.project_isolation import SessionResolver
                wins = SessionResolver(self.gateway).discover()
                present = [w for w in wins if w.window_id == wid]
                if not present:
                    return ComponentHealth("binding", HealthStatus.DISCONNECTED, f"window {wid} not connected (ids rotate on reconnect)")
                w = present[0]
                puid = getattr(s, "project_uuid", None)
                if puid and w.project_uuid and w.project_uuid != puid:
                    return ComponentHealth("binding", HealthStatus.DEGRADED, f"window {wid} hosts another project ({w.project_name})")
                return ComponentHealth("binding", HealthStatus.HEALTHY, f"window {wid} hosts {w.project_name or 'the project'}")
            except Exception as e:
                return ComponentHealth("binding", HealthStatus.UNVERIFIED, f"discovery failed: {e}")
        return ComponentHealth("binding", HealthStatus.UNVERIFIED, f"window {wid} bound by {getattr(s, 'bound_by', '?')}, not re-verified")

    def journal_health(self) -> ComponentHealth:
        if not self.project_path:
            return ComponentHealth("journal", HealthStatus.UNVERIFIED, "no project")
        try:
            from desk import ops
            pend = ops.pending(self.project_path)
        except Exception as e:
            return ComponentHealth("journal", HealthStatus.UNVERIFIED, f"unreadable: {e}")
        dirty = [p for p in pend if p.get("dirty")]
        if dirty:
            return ComponentHealth("journal", HealthStatus.DEGRADED, f"{len(dirty)} dirty operation(s): run desk.py recover")
        if pend:
            return ComponentHealth("journal", HealthStatus.DEGRADED, f"{len(pend)} unfinished operation(s)")
        return ComponentHealth("journal", HealthStatus.HEALTHY, "no pending operations")

    def engine_health(self) -> ComponentHealth:
        from desk.reliability.circuit_breaker import BreakerRegistry
        open_ = [k for k, v in BreakerRegistry.snapshot().items() if k.startswith("engine:") and v.get("state") == "OPEN"]
        if open_:
            return ComponentHealth("engine", HealthStatus.DEGRADED, f"breaker open: {', '.join(open_)}")
        return ComponentHealth("engine", HealthStatus.UNVERIFIED, "no run in this process")

    def snapshot(self, port: Optional[int] = None) -> Dict[str, Any]:
        comps = [self.binding_health(), self.journal_health(), self.engine_health()]
        if port is not None:
            comps.insert(0, self.gateway_health(port))
        worst = max(comps, key=lambda c: _ORDER.index(c.status)).status
        snap = {"ts": self.now(), "project": self.project_path, "status": worst.value, "components": [c.to_dict() for c in comps]}
        self.history.append(snap)
        if len(self.history) > 100:
            del self.history[:-100]
        return snap
