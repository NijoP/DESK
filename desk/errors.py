"""Typed DESK errors.

Every error a DESK library module raises for an *operator-facing* condition (project not bound,
bridge unreachable, writer lock held, approval missing) is a subclass of `DeskError`.

`DeskError` subclasses `SystemExit` on purpose:

* a command-line tool that does not catch it exits with the message on stderr and return code 1,
  exactly as the previous bare `raise SystemExit("STOP: ...")` did, so no tool output changes;
* a library caller (the agent loop, the rework executor, a test) can catch the precise type
  instead of catching `SystemExit`, which would also swallow a real interpreter exit.

`ops.write_op` keeps treating a `DeskError` as a *clean* failure (the board was not touched)
unless the error says `possibly_mutated = True` (a bridge timeout during a mutation).

Zero external dependencies.
"""
from typing import Any


class DeskError(SystemExit):
    exit_code: int = 1
    possibly_mutated: bool = False

    def __init__(self, message: str = "", **context: Any):
        super().__init__(message)
        self.message = message
        self.context = context

    def __str__(self) -> str:
        return self.message

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.message!r})"


class UsageError(DeskError):
    """Wrong command-line usage: the usage text is printed and the tool exits 1 (unchanged behaviour)."""


class ProjectError(DeskError):
    """projects/<P>/project.json missing, unreadable or not bound to EasyEDA documents."""


class BridgeError(DeskError):
    """Base class for EasyEDA Pro API-gateway failures."""


class BridgeUnreachable(BridgeError):
    """No gateway answered on the expected port after the configured retries."""


class BridgeDocumentMismatch(BridgeError):
    """The active EasyEDA document is not the one the project is bound to (WRONG SHEET guard)."""


class BridgeScriptError(BridgeError):
    """EasyEDA executed the script and reported an error (EDA error, JS runtime error, HTTP error)."""


class BridgeMutationTimeout(BridgeError):
    """A mutating bridge call timed out: the board may be partially modified.

    `ops.write_op` journals the operation as dirty when it sees `possibly_mutated`.
    """
    possibly_mutated = True


class WriteLockHeld(DeskError):
    """Another live writer holds projects/<P>/state/write.lock."""


class PendingOperationError(DeskError):
    """An earlier operation on the same target is unfinished or dirty; run `desk.py recover`."""


class ApprovalRequired(DeskError):
    """A non-idempotent mutation was attempted without a recorded human approval
    while DESK_MUTATION_POLICY=require."""


class ConfigError(DeskError):
    """A configuration value failed validation (see `python desk.py config show`)."""
