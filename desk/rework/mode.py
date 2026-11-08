"""
DESK Mode Architecture and Natural-Language Intent Detection.
Manages mode registration (Design Mode, Rework Mode, Audit Mode) and provides
robust pattern matching for conversational intent recognition across AI coding agents.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple

DESK_MODE_DESIGN = "DESIGN_MODE"
DESK_MODE_REWORK = "REWORK_MODE"
DESK_MODE_AUDIT = "AUDIT_MODE"

ALL_MODES = [DESK_MODE_DESIGN, DESK_MODE_REWORK, DESK_MODE_AUDIT]

# Regular expressions for natural language recognition
REWORK_INTENT_PATTERNS = [
    re.compile(r"(?i)\bactivate\s+rework\s+mode\b"),
    re.compile(r"(?i)\brework\s+mode\b"),
    re.compile(r"(?i)\bi\s+want\s+to\s+rework\b"),
    re.compile(r"(?i)\brework\s+(an?\s+)?(existing\s+|this\s+|my\s+)?(pcb|board|project)\b"),
    re.compile(r"(?i)\bcontinue\s+(my\s+)?unfinished\s+(easyeda\s+)?(pcb|board|project)\b"),
    re.compile(r"(?i)\btake\s+this\s+(pcb|board|project)\s+to\s+manufacturing\s+readiness\b"),
    re.compile(r"(?i)\baudit\s+this\s+existing\s+(pcb|board|project)\b"),
    re.compile(r"(?i)\brepair\s+(an?\s+)?(existing\s+|this\s+|my\s+)?(pcb|board|project)\b"),
    re.compile(r"(?i)\brecover\s+(an?\s+)?(existing\s+|this\s+|my\s+)?(pcb|board|project)\b"),
    re.compile(r"(?i)\bwhat\s+remains\s+(on|in)\s+this\s+(pcb|board|project)\b"),
]

AUDIT_ONLY_PATTERNS = [
    re.compile(r"(?i)\bactivate\s+audit\s+mode\b"),
    re.compile(r"(?i)\baudit\s+only\b"),
    re.compile(r"(?i)\bread-?only\s+inspection\b"),
    re.compile(r"(?i)\binspect\s+(this\s+)?(pcb|board)\s+without\s+modifying\b"),
]

NEW_DESIGN_PATTERNS = [
    re.compile(r"(?i)\bstart\s+a\s+new\s+(pcb|board|project)\b"),
    re.compile(r"(?i)\bcreate\s+a\s+new\s+(pcb|board|project)\b"),
    re.compile(r"(?i)\bdesign\s+a\s+new\s+(pcb|board|project)\b"),
    re.compile(r"(?i)\bgenerate\s+from\s+scratch\b"),
]


def detect_mode_intent(prompt: str) -> Tuple[str, float]:
    """
    Analyzes user prompt and returns (detected_mode, confidence_score).
    Default fallback is DESK_MODE_DESIGN if no specific intent is found.
    """
    if not prompt or not isinstance(prompt, str):
        return DESK_MODE_DESIGN, 0.0

    prompt_clean = prompt.strip()

    # 1. Check for explicit audit only
    for pat in AUDIT_ONLY_PATTERNS:
        if pat.search(prompt_clean):
            return DESK_MODE_AUDIT, 0.95

    # 2. Check for rework intent
    for pat in REWORK_INTENT_PATTERNS:
        if pat.search(prompt_clean):
            return DESK_MODE_REWORK, 0.95

    # 3. Check for new design intent
    for pat in NEW_DESIGN_PATTERNS:
        if pat.search(prompt_clean):
            return DESK_MODE_DESIGN, 0.90

    # Fallback default
    return DESK_MODE_DESIGN, 0.50


def is_rework_intent(prompt: str) -> bool:
    """Returns True if the prompt expresses an intent to activate Rework Mode."""
    mode, conf = detect_mode_intent(prompt)
    return mode in {DESK_MODE_REWORK, DESK_MODE_AUDIT} and conf >= 0.80
