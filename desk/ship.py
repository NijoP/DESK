"""
DESK Ship Command & Captain-FirstMate Bridge Architecture.

Implements the Firstmate-inspired nautical command hierarchy:
- Captain: Human lead electronics engineer holding ultimate decision authority.
- First Mate: Primary AI coordinator, bridge operator, greeting responder, and workflow orchestrator.
- Crew: Ephemeral task workers for discrete Ship Tasks.
- Scouts: Read-only reconnaissance workers.

Provides deterministic greeting detection, mission classification (Ship vs Scout),
and Captain approval boundaries. Pure Python standard library with zero external dependencies.
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


class MissionType(str, enum.Enum):
    """Categorization of instructions arriving at the Bridge."""
    GREETING = "GREETING"
    SCOUT_TASK = "SCOUT_TASK"
    SHIP_TASK = "SHIP_TASK"
    BRIDGE_CONTROL = "BRIDGE_CONTROL"


# Regex patterns identifying simple greetings
GREETING_PATTERNS = [
    r"^\s*hi\b",
    r"^\s*hello\b",
    r"^\s*hey\b",
    r"^\s*good\s+(morning|afternoon|evening|day)\b",
    r"^\s*greetings\b",
    r"^\s*yo\b",
]

# Action verbs typically indicating a mutating Ship Task
SHIP_TASK_KEYWORDS = [
    "route", "reroute", "place", "move", "pour", "repour", "create", "delete",
    "modify", "add", "commit", "build", "generate", "stitch", "wire", "connect",
    "update", "assign", "compile", "release",
]

# Action verbs and nouns indicating a read-only Scout Task
SCOUT_TASK_KEYWORDS = [
    "check", "audit", "find", "search", "query", "status", "show", "list",
    "inspect", "explain", "calculate", "calc", "verify", "measure", "read",
    "view", "report", "brief", "summarize", "drc",
]


class ShipBridge:
    """
    Coordinates Bridge operations between the Captain and First Mate.
    Ensures that simple greetings never spawn heavy computational workloads.
    """

    @staticmethod
    def is_simple_greeting(text: str) -> bool:
        """
        Determines if the instruction is solely or primarily a friendly greeting.
        Simple greetings must NOT trigger project scans, EDA calls, or worker crew spawning.
        """
        text_clean = text.strip().lower()
        # Fast exit if lengthy (complex command)
        if len(text_clean.split()) > 6:
            return False

        # Match known greeting prefixes
        for pattern in GREETING_PATTERNS:
            if re.match(pattern, text_clean):
                # Ensure no operational keywords follow (neither ship tasks nor scout audits)
                all_operational = SHIP_TASK_KEYWORDS + SCOUT_TASK_KEYWORDS
                words = set(re.findall(r"\w+", text_clean))
                if not any(kw in words for kw in all_operational):
                    return True
        return False

    @staticmethod
    def classify_mission(text: str) -> MissionType:
        """
        Classifies incoming instruction into GREETING, SCOUT_TASK, SHIP_TASK, or BRIDGE_CONTROL.
        """
        text_clean = text.strip().lower()

        if ShipBridge.is_simple_greeting(text_clean):
            return MissionType.GREETING

        # Check for Bridge emergency / control instructions
        if any(cmd in text_clean for cmd in ["all stop", "abort", "halt", "emergency stop", "status brief"]):
            return MissionType.BRIDGE_CONTROL

        # Count keyword hits for Ship vs Scout
        words = set(re.findall(r"\w+", text_clean))
        ship_hits = sum(1 for kw in SHIP_TASK_KEYWORDS if kw in words)
        scout_hits = sum(1 for kw in SCOUT_TASK_KEYWORDS if kw in words)

        # Explicit modifiers override
        if "scout" in words or "audit" in words or "investigate" in words:
            return MissionType.SCOUT_TASK
        if "ship" in words or "deliverable" in words or "route" in words or "pour" in words:
            return MissionType.SHIP_TASK

        if ship_hits > scout_hits:
            return MissionType.SHIP_TASK
        return MissionType.SCOUT_TASK

    @staticmethod
    def format_greeting_response(custom_message: Optional[str] = None) -> str:
        """
        Generates a respectful, disciplined nautical greeting addressing the user as Captain.
        """
        if custom_message:
            return f"Good day, Captain. {custom_message}"
        return (
            "Good day, Captain. First Mate standing by on the bridge.\n"
            "All systems nominal and waiting on your orders for the board."
        )

    @staticmethod
    def requires_captain_approval(operation_id: str, params: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
        """
        Evaluates whether an operation crosses the authority threshold and mandates
        explicit Captain sign-off before proceeding.
        """
        op_id_lower = operation_id.lower()
        # Destructive deletions or full clear (avoiding matching 'clearance')
        if "delete" in op_id_lower or "clear_block" in op_id_lower or "clear_canvas" in op_id_lower or "wipe" in op_id_lower:
            return True, "Operation involves destructive geometry removal on the active board."

        # Manufacturing releases
        if "release" in op_id_lower or "gerber_export" in op_id_lower:
            return True, "Manufacturing package generation requires formal Captain sign-off."

        # High-voltage clearance waivers
        if params and params.get("clearance_mm", 1.0) < 0.2:
            return True, "Clearance rule is below minimum manufacturing safety margin (0.2 mm)."

        return False, ""
