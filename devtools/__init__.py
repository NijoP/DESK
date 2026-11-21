"""Development-time tooling for working ON DESK (not part of the `desk` product package).

Nothing under `desk/` may import this package (AGENTS.md section B; enforced by tests/test_learn.py
TestDevelopmentBoundary). It is excluded from the wheel by pyproject's `include = ["desk*"]`.
"""
