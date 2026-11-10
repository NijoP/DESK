# DESK Engineering Learning Repository

This directory contains DESK's accumulated engineering experience, documented as incidents, lessons, and known failure patterns.

## Purpose

Transform every significant engineering mistake into reusable knowledge that makes DESK progressively more reliable.

## Structure

```
learning/
├── README.md                 # This file
├── LEARNING_PRINCIPLES.md    # Core learning methodology
├── INCIDENT_TEMPLATE.md      # Template for incident reports
├── LESSON_TEMPLATE.md        # Template for reusable lessons
├── SESSION_TEMPLATE.md       # Template for session logs
├── incidents/                # Individual incident reports
│   └── README.md
├── lessons/                  # Extracted reusable engineering lessons
│   └── README.md
├── playbooks/                # Recovery and prevention procedures
│   └── README.md
├── sessions/                 # Session-level engineering logs
│   └── README.md
└── index/                    # Searchable indices
    ├── INCIDENT_INDEX.md
    ├── LESSON_INDEX.md
    └── KNOWN_FAILURES.md
```

## Usage for AI Agents

**Before starting any engineering task:**

1. Read `index/KNOWN_FAILURES.md` to identify relevant failure patterns
2. Search `lessons/` for applicable preventive rules
3. Check `sessions/` for similar previous work

**During execution:**

1. Record intended operations and actual results in `sessions/`
2. When a significant failure occurs, create an incident in `incidents/`
3. Document recovery attempts and successful solutions
4. Extract reusable lessons to `lessons/`

**After execution:**

1. Review the session for unrecorded mistakes
2. Update `index/INCIDENT_INDEX.md` and `index/LESSON_INDEX.md`
3. Add new failure patterns to `index/KNOWN_FAILURES.md`

## Usage for Human Engineers

The same principles apply. This repository is the canonical source of DESK's engineering experience.

## Incident ID Format

```
INC-YYYYMMDD-NNN
```
Example: `INC-20251111-001`

## Lesson ID Format

```
LSN-YYYYMMDD-NNN
```
Example: `LSN-20251111-001`

## Known Failure ID Format

```
KF-YYYYMMDD-NNN
```
Example: `KF-20251111-001`

## Confidentiality

Never include API keys, authentication tokens, passwords, or credentials in any document.
Sanitize all parameters before recording.