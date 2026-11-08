"""
DESK Execution State Projection & Mission Control State Machine.

Maintains an in-memory and disk-reconciled projection of the 12 canonical engineering stages,
calculating honest progress from measurable task units, streaming real-time metrics,
and reconciling interrupted work after system restart.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from desk.runtime.events import Event, EventBus, get_event_bus
from desk.runtime.resource_profile import ResourceDetector

# The 12 Canonical Engineering Stages
STAGE_REQUIREMENT_INGESTION = "requirement_ingestion"
STAGE_SCHEMATIC_INTELLIGENCE = "schematic_intelligence"
STAGE_COMPONENT_INTELLIGENCE = "component_intelligence"
STAGE_ELECTRICAL_VERIFICATION = "electrical_verification"
STAGE_PCB_INGESTION = "pcb_ingestion"
STAGE_PLACEMENT_INTELLIGENCE = "placement_intelligence"
STAGE_ROUTING_PREPARATION = "routing_preparation"
STAGE_PCB_ROUTING = "pcb_routing"
STAGE_COPPER_GENERATION = "copper_generation"
STAGE_DRC_VERIFICATION = "drc_verification"
STAGE_MANUFACTURING_VERIFICATION = "manufacturing_verification"
STAGE_ENGINEERING_REPORT = "engineering_report"

CANONICAL_STAGES = [
    STAGE_REQUIREMENT_INGESTION,
    STAGE_SCHEMATIC_INTELLIGENCE,
    STAGE_COMPONENT_INTELLIGENCE,
    STAGE_ELECTRICAL_VERIFICATION,
    STAGE_PCB_INGESTION,
    STAGE_PLACEMENT_INTELLIGENCE,
    STAGE_ROUTING_PREPARATION,
    STAGE_PCB_ROUTING,
    STAGE_COPPER_GENERATION,
    STAGE_DRC_VERIFICATION,
    STAGE_MANUFACTURING_VERIFICATION,
    STAGE_ENGINEERING_REPORT,
]

STAGE_NAMES = {
    STAGE_REQUIREMENT_INGESTION: "1. Requirement Ingestion (Gate R)",
    STAGE_SCHEMATIC_INTELLIGENCE: "2. Schematic Intelligence (M1)",
    STAGE_COMPONENT_INTELLIGENCE: "3. Component Intelligence & BOM (Gate B)",
    STAGE_ELECTRICAL_VERIFICATION: "4. Electrical Rules Verification (ERC)",
    STAGE_PCB_INGESTION: "5. PCB Ingestion & Stackup Analysis",
    STAGE_PLACEMENT_INTELLIGENCE: "6. Mechanical & Placement Analysis (M2)",
    STAGE_ROUTING_PREPARATION: "7. Routing Preparation & Escape Stubs",
    STAGE_PCB_ROUTING: "8. Autonomous PCB Routing (M3)",
    STAGE_COPPER_GENERATION: "9. Copper Plane & Polygon Generation (M4)",
    STAGE_DRC_VERIFICATION: "10. DRC & Electrical Verification (M5)",
    STAGE_MANUFACTURING_VERIFICATION: "11. Manufacturing Verification & DFM (M6)",
    STAGE_ENGINEERING_REPORT: "12. Final Engineering Report & Release",
}

STAGE_WEIGHTS = {
    STAGE_REQUIREMENT_INGESTION: 5.0,
    STAGE_SCHEMATIC_INTELLIGENCE: 10.0,
    STAGE_COMPONENT_INTELLIGENCE: 10.0,
    STAGE_ELECTRICAL_VERIFICATION: 5.0,
    STAGE_PCB_INGESTION: 5.0,
    STAGE_PLACEMENT_INTELLIGENCE: 10.0,
    STAGE_ROUTING_PREPARATION: 5.0,
    STAGE_PCB_ROUTING: 20.0,
    STAGE_COPPER_GENERATION: 10.0,
    STAGE_DRC_VERIFICATION: 10.0,
    STAGE_MANUFACTURING_VERIFICATION: 5.0,
    STAGE_ENGINEERING_REPORT: 5.0,
}

# Redaction patterns for logs
SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|secret|password|bearer\s+[a-zA-Z0-9_\-\.]+)\s*[:=]\s*([^\s,;]+)"),
    re.compile(r"(?i)(ghp_[a-zA-Z0-9]{20,}|sk-[a-zA-Z0-9_\-]{20,})"),
]


def redact_sensitive(text: str) -> str:
    """Sanitizes credentials, tokens, and secrets from user-visible logs."""
    if not isinstance(text, str):
        return str(text)
    sanitized = text
    for pat in SECRET_PATTERNS:
        sanitized = pat.sub("[REDACTED]", sanitized)
    return sanitized


@dataclass
class StageState:
    stage_id: str
    display_name: str
    status: str = "PENDING"  # PENDING, QUEUED, RUNNING, COMPLETED, FAILED, BLOCKED, CANCELLED, SKIPPED, UNKNOWN
    start_time: Optional[float] = None
    completion_time: Optional[float] = None
    duration_s: float = 0.0
    progress: Optional[float] = None  # 0.0 to 100.0 or None if indeterminate
    current_activity: str = ""
    output_summary: str = ""
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    artifacts: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        duration = self.duration_s
        if self.status == "RUNNING" and self.start_time:
            duration = max(0.0, round(time.time() - self.start_time, 2))
        return {
            "stage_id": self.stage_id,
            "display_name": self.display_name,
            "status": self.status,
            "start_time": self.start_time,
            "completion_time": self.completion_time,
            "duration_s": duration,
            "progress": self.progress,
            "current_activity": self.current_activity,
            "output_summary": self.output_summary,
            "warnings_count": len(self.warnings),
            "errors_count": len(self.errors),
            "warnings": self.warnings[-10:],
            "errors": self.errors[-10:],
            "artifacts": self.artifacts,
        }


class ExecutionProjection:
    """Consolidated state projector maintaining real-time execution telemetry."""

    def __init__(self, project_id: str = "projects/WATCH", event_bus: Optional[EventBus] = None) -> None:
        self.project_id = project_id
        self.event_bus = event_bus or get_event_bus()
        self._lock = threading.RLock()

        self.execution_id: str = f"exec_{int(time.time())}_{os.getpid()}"
        self.status: str = "IDLE"  # IDLE, RUNNING, COMPLETED, FAILED, INTERRUPTED
        self.start_time: Optional[float] = None
        self.completion_time: Optional[float] = None
        self.current_stage: Optional[str] = None
        self.current_task: Optional[str] = None
        self.current_activity: str = "Standing by for authorized engineering operations."
        self.last_checkpoint: Optional[str] = None

        # 12 canonical stages
        self.stages: Dict[str, StageState] = {
            s: StageState(stage_id=s, display_name=STAGE_NAMES[s]) for s in CANONICAL_STAGES
        }

        # Activity feed and diagnostic logs
        self.timeline: List[Dict[str, Any]] = []
        self.logs: List[Dict[str, Any]] = []
        self.max_timeline: int = 500
        self.max_logs: int = 1000

        # Real engineering results
        self.engineering_results: Dict[str, Any] = {
            "components_processed": 0,
            "nets_analyzed": 0,
            "tracks_generated": 0,
            "vias_generated": 0,
            "copper_zones_processed": 0,
            "drc_violations": 0,
            "unconnected_nets": 0,
            "critical_nets_status": "NOT_RUN",
            "quality_gates": {
                "gate_1_shorts": "NOT_RUN",
                "gate_2_unconnected": "NOT_RUN",
                "gate_3_clearance": "NOT_RUN",
                "gate_4_critical_nets": "NOT_RUN",
                "gate_5_stackup": "NOT_RUN",
                "gate_6_copper_continuity": "NOT_RUN",
                "gate_7_electrical": "NOT_RUN",
                "gate_8_manufacturing": "NOT_RUN",
            },
            "manufacturing_quote": None,
            "final_acceptance_state": "PENDING",
            "evidence_status": "STALE",
        }

        # Wire event listener
        self.event_bus.subscribe("*", self._handle_event)

        # Attempt to reconcile previous interrupted state from disk
        self._reconcile_restart_state()

    def set_project(self, project_id: str) -> None:
        """Switches the active project context and reconciles its state."""
        with self._lock:
            self.project_id = project_id
            self._reconcile_restart_state()

    def _state_file_path(self) -> str:
        d = os.path.join(self.project_id, "state") if os.path.exists(self.project_id) else "state"
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, "execution_state.json")

    def _reconcile_restart_state(self) -> None:
        """Restores persisted execution state and marks interrupted work honestly."""
        fpath = self._state_file_path()
        if not os.path.exists(fpath):
            return

        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)

            # If previous state was running but process changed, mark as INTERRUPTED
            prev_status = data.get("status", "IDLE")
            prev_pid = data.get("pid")
            is_stale = prev_status == "RUNNING" and (prev_pid != os.getpid())

            self.execution_id = data.get("execution_id", self.execution_id)
            self.status = "INTERRUPTED" if is_stale else prev_status
            self.start_time = data.get("start_time")
            self.completion_time = data.get("completion_time")
            self.current_stage = data.get("current_stage")
            self.current_task = data.get("current_task")
            self.current_activity = "Session interrupted by shutdown/restart." if is_stale else data.get("current_activity", "")
            self.last_checkpoint = data.get("last_checkpoint")

            # Restore stages
            for sid, sdata in data.get("stages", {}).items():
                if sid in self.stages:
                    st = self.stages[sid]
                    st.status = "INTERRUPTED" if is_stale and sdata.get("status") == "RUNNING" else sdata.get("status", "PENDING")
                    st.start_time = sdata.get("start_time")
                    st.completion_time = sdata.get("completion_time")
                    st.duration_s = sdata.get("duration_s", 0.0)
                    st.progress = sdata.get("progress")
                    st.current_activity = sdata.get("current_activity", "")
                    st.output_summary = sdata.get("output_summary", "")

            # Restore engineering results
            if "engineering_results" in data:
                self.engineering_results.update(data["engineering_results"])
                if is_stale:
                    self.engineering_results["evidence_status"] = "STALE"

            # Add restart reconciliation timeline entry
            if is_stale:
                self._record_timeline_entry(
                    severity="WARNING",
                    stage=self.current_stage or "SYSTEM",
                    message="Recovered from restart: Previous active operation was interrupted. Reconciled honestly as INTERRUPTED.",
                )
        except Exception:
            pass

    def persist_state(self) -> None:
        """Persists current execution state atomically to disk."""
        with self._lock:
            fpath = self._state_file_path()
            payload = {
                "execution_id": self.execution_id,
                "project_id": self.project_id,
                "pid": os.getpid(),
                "status": self.status,
                "start_time": self.start_time,
                "completion_time": self.completion_time,
                "current_stage": self.current_stage,
                "current_task": self.current_task,
                "current_activity": self.current_activity,
                "last_checkpoint": self.last_checkpoint,
                "stages": {s: self.stages[s].to_dict() for s in CANONICAL_STAGES},
                "engineering_results": self.engineering_results,
                "updated_at": time.time(),
            }

            try:
                tmp_path = f"{fpath}.tmp"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2)
                os.replace(tmp_path, fpath)
            except Exception:
                pass

    def _handle_event(self, ev: Event) -> None:
        """Updates projection state in response to dispatched events."""
        with self._lock:
            t = ev.event_type
            stage_id = ev.stage or self.current_stage

            # Record timeline entry for significant events
            if t.startswith("stage.") or t.startswith("task.") or t.startswith("checkpoint.") or ev.error:
                sev = "ERROR" if ev.error or "fail" in t else ("WARNING" if "warn" in t else "INFO")
                msg = ev.message or f"{t}: {ev.task or stage_id}"
                self._record_timeline_entry(sev, stage_id or "SYSTEM", msg, ev.timestamp)

            # Record diagnostic log
            if ev.message or ev.error:
                lvl = "ERROR" if ev.error else ("WARNING" if "warn" in t else ("DEBUG" if "debug" in t else "INFO"))
                self._record_log_entry(lvl, stage_id or "SYSTEM", ev.task or "", ev.message or ev.error or "", ev.timestamp)

            # Stage lifecycle
            if t == "stage.start" and stage_id in self.stages:
                if self.status == "IDLE":
                    self.status = "RUNNING"
                    self.start_time = ev.timestamp

                self.current_stage = stage_id
                self.current_task = ev.task or stage_id
                self.current_activity = ev.message or f"Executing {STAGE_NAMES.get(stage_id, stage_id)}"

                st = self.stages[stage_id]
                st.status = "RUNNING"
                st.start_time = ev.timestamp
                st.progress = ev.progress
                st.current_activity = self.current_activity

            elif t == "stage.progress" and stage_id in self.stages:
                st = self.stages[stage_id]
                if st.status != "RUNNING":
                    st.status = "RUNNING"
                    if not st.start_time:
                        st.start_time = ev.timestamp

                if ev.progress is not None:
                    st.progress = min(100.0, max(0.0, round(ev.progress, 1)))
                if ev.message:
                    st.current_activity = ev.message
                    self.current_activity = ev.message
                if ev.metrics:
                    self._update_results_from_metrics(ev.metrics)

            elif t == "stage.complete" and stage_id in self.stages:
                st = self.stages[stage_id]
                st.status = "COMPLETED"
                st.completion_time = ev.timestamp
                st.progress = 100.0
                st.duration_s = max(0.0, round(ev.timestamp - (st.start_time or ev.timestamp), 2))
                st.output_summary = ev.message or "Completed successfully."
                st.current_activity = "Completed"

                if ev.artifacts:
                    st.artifacts.extend(ev.artifacts)

                # Check if all stages completed
                if all(self.stages[s].status in {"COMPLETED", "SKIPPED"} for s in CANONICAL_STAGES):
                    self.status = "COMPLETED"
                    self.completion_time = ev.timestamp
                    self.current_activity = "All engineering stages successfully completed and verified."
                    self.engineering_results["final_acceptance_state"] = "ACCEPTED"
                    self.engineering_results["evidence_status"] = "FRESH"

            elif t == "stage.fail" and stage_id in self.stages:
                st = self.stages[stage_id]
                st.status = "FAILED"
                st.completion_time = ev.timestamp
                st.errors.append(ev.error or ev.message or "Stage failed.")
                st.duration_s = max(0.0, round(ev.timestamp - (st.start_time or ev.timestamp), 2))
                st.current_activity = f"Failed: {ev.error or ev.message}"

                self.status = "FAILED"
                self.current_activity = f"Execution blocked at {STAGE_NAMES.get(stage_id, stage_id)}: {ev.error or ev.message}"
                self.engineering_results["final_acceptance_state"] = "BLOCKED"

            elif t == "stage.skip" and stage_id in self.stages:
                st = self.stages[stage_id]
                st.status = "SKIPPED"
                st.output_summary = ev.message or "Skipped per design profile."
                st.current_activity = "Skipped"

            elif t == "checkpoint.saved":
                chk_id = ev.payload.get("checkpoint_id") or ev.message
                self.last_checkpoint = chk_id
                if stage_id in self.stages and chk_id:
                    self.stages[stage_id].artifacts.append({"type": "checkpoint", "id": chk_id})

            elif t == "results.update":
                self._update_results_from_metrics(ev.payload or ev.metrics)

            self.persist_state()

    def _update_results_from_metrics(self, data: Dict[str, Any]) -> None:
        """Merges metrics and results from engineering operations."""
        if not data:
            return
        for k in [
            "components_processed",
            "nets_analyzed",
            "tracks_generated",
            "vias_generated",
            "copper_zones_processed",
            "drc_violations",
            "unconnected_nets",
            "critical_nets_status",
            "manufacturing_quote",
            "evidence_status",
            "final_acceptance_state",
        ]:
            if k in data:
                self.engineering_results[k] = data[k]

        if "quality_gates" in data and isinstance(data["quality_gates"], dict):
            self.engineering_results["quality_gates"].update(data["quality_gates"])

    def _record_timeline_entry(self, severity: str, stage: str, message: str, timestamp: Optional[float] = None) -> None:
        ts = timestamp or time.time()
        time_str = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).strftime("%H:%M:%S")
        entry = {
            "id": f"tl_{len(self.timeline) + 1}",
            "timestamp": ts,
            "time_str": time_str,
            "severity": severity,
            "stage": stage,
            "message": redact_sensitive(message),
        }
        self.timeline.append(entry)
        if len(self.timeline) > self.max_timeline:
            self.timeline.pop(0)

    def _record_log_entry(self, level: str, stage: str, task: str, message: str, timestamp: Optional[float] = None) -> None:
        ts = timestamp or time.time()
        time_str = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).strftime("%H:%M:%S.%f")[:-3]
        entry = {
            "id": f"log_{len(self.logs) + 1}",
            "timestamp": ts,
            "time_str": time_str,
            "level": level,
            "stage": stage,
            "task": task,
            "message": redact_sensitive(message),
        }
        self.logs.append(entry)
        if len(self.logs) > self.max_logs:
            self.logs.pop(0)

    def calculate_overall_progress(self) -> float:
        """Calculates honest weighted progress based on completed and active stages."""
        with self._lock:
            if self.status == "COMPLETED":
                return 100.0

            progress = 0.0
            for stage_id, weight in STAGE_WEIGHTS.items():
                st = self.stages[stage_id]
                if st.status == "COMPLETED" or st.status == "SKIPPED":
                    progress += weight
                elif st.status == "RUNNING" and st.progress is not None:
                    progress += weight * (st.progress / 100.0)

            # Never report 100% until the entire pipeline is verified complete
            return min(99.9, round(progress, 1))

    def get_summary(self) -> Dict[str, Any]:
        """Returns the high-density executive status for UI and CLI."""
        with self._lock:
            hw = ResourceDetector.detect().to_dict()

            completed_count = sum(1 for s in self.stages.values() if s.status == "COMPLETED")
            pending_count = sum(1 for s in self.stages.values() if s.status in {"PENDING", "QUEUED"})
            failed_count = sum(1 for s in self.stages.values() if s.status == "FAILED")
            warning_count = sum(len(s.warnings) for s in self.stages.values())

            duration = 0.0
            if self.start_time:
                end_t = self.completion_time or time.time()
                duration = max(0.0, round(end_t - self.start_time, 2))

            return {
                "execution_id": self.execution_id,
                "project_id": self.project_id,
                "status": self.status,
                "overall_progress": self.calculate_overall_progress(),
                "current_stage": self.current_stage,
                "current_stage_name": STAGE_NAMES.get(self.current_stage or "", "None"),
                "current_task": self.current_task,
                "current_activity": self.current_activity,
                "last_checkpoint": self.last_checkpoint,
                "duration_s": duration,
                "completed_stages": completed_count,
                "pending_stages": pending_count,
                "failed_stages": failed_count,
                "warning_count": warning_count,
                "stages": {s: self.stages[s].to_dict() for s in CANONICAL_STAGES},
                "engineering_results": self.engineering_results,
                "metrics": {
                    "process_ram_mb": hw["current_process_ram_mb"],
                    "available_ram_mb": hw["available_ram_mb"],
                    "logical_cores": hw["logical_cores"],
                    "resource_tier": hw["resource_tier"],
                    "memory_pressure": hw["memory_pressure"],
                },
                "updated_at": time.time(),
                "iso_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }

    def get_timeline(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Returns the chronological activity feed."""
        with self._lock:
            return list(self.timeline[-limit:])

    def get_logs(self, level: Optional[str] = None, search: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
        """Returns filtered diagnostic logs."""
        with self._lock:
            logs = self.logs
            if level and level.upper() != "ALL":
                lvl = level.upper()
                logs = [l for l in logs if l["level"] == lvl]
            if search:
                s = search.lower()
                logs = [l for l in logs if s in l["message"].lower() or s in l["stage"].lower() or s in l["task"].lower()]
            return list(logs[-limit:])


# Singleton projector
_GLOBAL_PROJECTION: Optional[ExecutionProjection] = None


def get_execution_projection(project_id: str = "projects/WATCH") -> ExecutionProjection:
    """Returns or initializes the global execution state projection."""
    global _GLOBAL_PROJECTION
    if _GLOBAL_PROJECTION is None:
        _GLOBAL_PROJECTION = ExecutionProjection(project_id=project_id)
    return _GLOBAL_PROJECTION
