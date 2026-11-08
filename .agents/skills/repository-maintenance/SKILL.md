---
name: repository-maintenance
description: Test suite execution, linting, git commit discipline, and Backpass memory optimization passes.
triggers:
  - "maintenance"
  - "backpass"
  - "memory optimization"
  - "test suite"
  - "commit"
  - "git status"
inputs:
  action: string
  reviewer: string
outputs:
  clean_working_copy: boolean
  all_tests_passed: boolean
authoritative_pipeline: INFRA
replay_safety: SAFE_IDEMPOTENT
---

# Repository Maintenance Skill

## Purpose
Maintains repository health, validates test suite integrity, enforces Git hygiene, and oversees periodic Backpass agent memory optimization passes.

## When to Use
- Concluding development milestones before creating release pull requests.
- Running the full 195+ test suite across all subsystems.
- Scanning development transcripts with Backpass and reviewing proposed memory edits.

## Required Inputs
- Target action (`test`, `lint`, `backpass_scan`, `backpass_optimize`).
- Reviewer signature for human-gated memory changes.

## Relevant DESK Modules
- `tests/test_*.py`: Full Python test suite.
- `backpass`: Agent memory gradient descent CLI.
- `.backpassrc.json`: Project memory configuration.

## Required Engineering Constraints
- Zero Failing Tests: Never commit code when tests fail.
- Non-Destructive Memory Updates: Never automatically apply Backpass memory edits without human review (`backpass apply --no-ui`).
- Git Discipline: Do not commit untracked cache directories (`.backpass/`, `__pycache__/`, `*.db`).

## Recommended Workflow
1. Execute full Python test suite: `python -m unittest discover -s tests -p "test_*.py"`.
2. Inspect git status for untracked or dirty state: `git status`.
3. Scan recent agent sessions: `backpass scan --since 7d`.
4. Run memory optimization pass: `backpass`.
5. Review proposed memory edits with Captain: `backpass apply --no-ui`.
6. Verify memory budget and status: `backpass status`.

## Validation Steps
- Verify Backpass status: `backpass status`.
- Ensure clean Git diff: `git diff --stat`.

## Failure Conditions & Recovery
- Test failure: Immediately investigate traceback and revert breaking edits.
- Memory budget exceeded: Extract overgrown instructions into specialized skills.

## Expected Output
- Clean repository working copy with 100% passing test suite and optimized, budgeted agent instructions.

## Documentation References
- [Backpass Architecture](file:///docs/development_memory/01_BACKPASS_ARCHITECTURE.md)
- [Daily Development Workflow](file:///docs/development_memory/07_DAILY_WORKFLOW.md)
