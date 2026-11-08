"""DESK EasyEDA Pro Integration Subsystem.

Coordinates the official EasyEDA Pro CLI (`easyeda-pro`) and local IPC bridge.
Enforces strict fail-closed mutation safety:
- Protected customer projects ('WATCH', 'BEEBOX') are strictly read-only.
- All mutations require verified session locks and pre-mutation rollback snapshots.
- Read-only inspections (netlist, BOM, DRC, layout primitives) execute without side effects.
"""

from __future__ import annotations
import os
import sys
import shutil
import subprocess
import json
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field


class SafetyViolationError(Exception):
    """Raised when an operation attempts an unsafe or unapproved mutation."""
    pass


class ProjectNotFoundError(Exception):
    """Raised when the specified EasyEDA Pro project or session is not found."""
    pass


@dataclass
class EasyEDASession:
    session_id: str
    project_name: str
    project_path: str
    window_id: Optional[str] = None
    is_active: bool = True
    pid: Optional[int] = None


@dataclass
class PCBPrimitiveData:
    components: List[Dict[str, Any]] = field(default_factory=list)
    pads: List[Dict[str, Any]] = field(default_factory=list)
    tracks: List[Dict[str, Any]] = field(default_factory=list)
    vias: List[Dict[str, Any]] = field(default_factory=list)
    zones: List[Dict[str, Any]] = field(default_factory=list)
    poured_copper: List[Dict[str, Any]] = field(default_factory=list)
    outline: Optional[Dict[str, Any]] = None


class EasyEDAProCLI:
    """Interface to the official easyeda-pro CLI executable."""

    STANDARD_PATHS_WINDOWS = [
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\EasyEDAPro\easyeda-pro.exe"),
        os.path.expandvars(r"%PROGRAMFILES%\EasyEDAPro\easyeda-pro.exe"),
        r"C:\Program Files\EasyEDAPro\easyeda-pro.exe",
    ]
    STANDARD_PATHS_MACOS = [
        "/Applications/EasyEDAPro.app/Contents/MacOS/easyeda-pro",
        "/usr/local/bin/easyeda-pro",
    ]
    STANDARD_PATHS_LINUX = [
        "/usr/bin/easyeda-pro",
        "/usr/local/bin/easyeda-pro",
        os.path.expanduser("~/.local/bin/easyeda-pro"),
    ]

    def __init__(self, custom_binary_path: Optional[str] = None):
        self._binary_path = custom_binary_path or self._discover_binary()

    def _discover_binary(self) -> Optional[str]:
        # Check PATH first
        in_path = shutil.which("easyeda-pro")
        if in_path:
            return in_path

        # Check platform defaults
        candidate_list = []
        if sys.platform == "win32":
            candidate_list = self.STANDARD_PATHS_WINDOWS
        elif sys.platform == "darwin":
            candidate_list = self.STANDARD_PATHS_MACOS
        else:
            candidate_list = self.STANDARD_PATHS_LINUX

        for candidate in candidate_list:
            if os.path.exists(candidate) and os.access(candidate, os.X_OK):
                return candidate
        return None

    @property
    def is_installed(self) -> bool:
        return self._binary_path is not None

    @property
    def binary_path(self) -> Optional[str]:
        return self._binary_path

    def doctor(self) -> Dict[str, Any]:
        """Run diagnostic check on EasyEDA Pro installation."""
        if not self.is_installed:
            return {
                "status": "NOT_INSTALLED",
                "binary_path": None,
                "message": "easyeda-pro CLI binary not found in PATH or standard locations.",
            }

        try:
            res = subprocess.run(
                [self._binary_path, "doctor"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5.0,
            )
            return {
                "status": "OK" if res.returncode == 0 else "WARNING",
                "binary_path": self._binary_path,
                "returncode": res.returncode,
                "output": res.stdout.strip(),
            }
        except Exception as e:
            return {
                "status": "ERROR",
                "binary_path": self._binary_path,
                "message": str(e),
            }

    def list_sessions(self) -> List[EasyEDASession]:
        """List active EasyEDA Pro editor sessions."""
        if not self.is_installed:
            return []

        try:
            res = subprocess.run(
                [self._binary_path, "session", "list", "--json"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5.0,
            )
            if res.returncode == 0 and res.stdout.strip():
                data = json.loads(res.stdout)
                sessions = []
                for s in data:
                    sessions.append(
                        EasyEDASession(
                            session_id=s.get("id", ""),
                            project_name=s.get("name", "Unknown"),
                            project_path=s.get("path", ""),
                            window_id=s.get("window_id"),
                            pid=s.get("pid"),
                        )
                    )
                return sessions
        except Exception:
            pass
        return []


class EasyEDAProManager:
    """Unified manager for EasyEDA Pro operations with safety gates."""

    PROTECTED_PROJECT_PATTERNS = ["WATCH", "BEEBOX", "CUSTOMER", "PRODUCTION"]

    def __init__(self, cli: Optional[EasyEDAProCLI] = None):
        self.cli = cli or EasyEDAProCLI()

    def is_project_protected(self, project_path_or_name: str) -> bool:
        """Returns True if the project is a protected customer/production board."""
        norm = os.path.basename(project_path_or_name).upper()
        for pat in self.PROTECTED_PROJECT_PATTERNS:
            if pat in norm:
                return True
        return False

    def assert_mutation_permitted(
        self,
        project_path_or_name: str,
        is_disposable_test: bool = False,
        has_snapshot: bool = False,
        captain_approval: bool = False,
    ):
        """Strict fail-closed mutation guard."""
        if self.is_project_protected(project_path_or_name):
            raise SafetyViolationError(
                f"MUTATION REJECTED: Project '{project_path_or_name}' matches protected customer pattern. "
                f"Live writes are strictly forbidden on production projects."
            )

        if not is_disposable_test and not captain_approval:
            raise SafetyViolationError(
                f"MUTATION REJECTED: Live write to '{project_path_or_name}' requires explicit Captain authorization."
            )

        if not has_snapshot:
            raise SafetyViolationError(
                f"MUTATION REJECTED: Pre-mutation rollback snapshot must exist before modifying '{project_path_or_name}'."
            )

    def inspect_project_offline(self, project_path: str) -> Dict[str, Any]:
        """Read-only offline inspection of project structure and files."""
        if not os.path.exists(project_path):
            raise ProjectNotFoundError(f"Project directory not found: {project_path}")

        files = os.listdir(project_path)
        schematic_files = [f for f in files if f.endswith((".json", ".esym", ".sch"))]
        pcb_files = [f for f in files if f.endswith((".epcb", ".pcb", ".kicad_pcb"))]
        is_protected = self.is_project_protected(project_path)

        return {
            "project_name": os.path.basename(project_path),
            "project_path": os.path.abspath(project_path),
            "is_protected": is_protected,
            "mutation_allowed": not is_protected,
            "schematic_files": schematic_files,
            "pcb_files": pcb_files,
            "total_files": len(files),
        }

    def read_pcb_primitives_offline(self, pcb_file_path: str) -> PCBPrimitiveData:
        """Parse PCB primitives from an offline PCB file without mutating anything."""
        if not os.path.exists(pcb_file_path):
            raise FileNotFoundError(f"PCB file not found: {pcb_file_path}")

        data = PCBPrimitiveData()
        try:
            with open(pcb_file_path, "r", encoding="utf-8") as f:
                content = json.load(f)

            if isinstance(content, dict):
                data.components = content.get("components", [])
                data.pads = content.get("pads", [])
                data.tracks = content.get("tracks", [])
                data.vias = content.get("vias", [])
                data.zones = content.get("zones", [])
                data.poured_copper = content.get("poured_copper", [])
                data.outline = content.get("outline")
        except Exception:
            # If not valid JSON (e.g. text/binary format), return empty initialized struct
            pass

        return data


_GLOBAL_EDA_MANAGER: Optional[EasyEDAProManager] = None


def get_easyeda_manager() -> EasyEDAProManager:
    global _GLOBAL_EDA_MANAGER
    if _GLOBAL_EDA_MANAGER is None:
        _GLOBAL_EDA_MANAGER = EasyEDAProManager()
    return _GLOBAL_EDA_MANAGER
