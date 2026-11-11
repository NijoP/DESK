"""Crash-safe file writes for DESK state and identity files.

A plain `open(path, "w")` followed by `json.dump` leaves a truncated file if the
process dies mid-write. For files that define project identity (project.json),
board state (pcb_dump.json) or approvals, that is data loss. Every writer of
such a file goes through `atomic_write_json` / `atomic_write_text`: the content
is written to a sibling temp file, flushed to disk, then renamed over the target
with `os.replace`, which is atomic on POSIX and NTFS.

Zero external dependencies.
"""
import json
import os
import tempfile
from typing import Any, Optional


def atomic_write_text(path: str, text: str, encoding: str = "utf-8") -> None:
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", suffix=os.path.basename(path), dir=directory)
    try:
        with os.fdopen(fd, "w", encoding=encoding) as h:
            h.write(text)
            h.flush()
            os.fsync(h.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def atomic_write_json(path: str, obj: Any, indent: Optional[int] = 1, sort_keys: bool = False) -> None:
    atomic_write_text(path, json.dumps(obj, indent=indent, sort_keys=sort_keys, ensure_ascii=False) + ("\n" if indent else ""))


def read_json(path: str, default: Any = None) -> Any:
    """Read JSON, returning `default` if the file is missing or unparsable."""
    try:
        with open(path, encoding="utf-8") as h:
            return json.load(h)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default
