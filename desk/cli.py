"""Console entry point for DESK.

Installed by pyproject.toml as the `desk` command (`pip install -e .`), also usable as
`python -m desk.cli`. Everything except `--version` is delegated to tools/desk.py's
`main(argv)`, which must live next to this package (a clone or an editable install).
"""
import importlib.util
import os
import sys
from typing import List, Optional

from desk._version import __version__

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TOOLS = os.path.join(_REPO, "tools")


def load_tool_main():
    """Load tools/desk.py under a private module name (it would shadow the `desk` package otherwise)."""
    path = os.path.join(_TOOLS, "desk.py")
    if not os.path.exists(path):
        raise FileNotFoundError(f"{path} not found: run from a clone of the repository or `pip install -e .`")
    if _TOOLS not in sys.path:
        sys.path.insert(0, _TOOLS)
    spec = importlib.util.spec_from_file_location("desk_tool_cli", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod.main


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("--version", "-V", "version"):
        print(f"desk {__version__} (Python {sys.version.split()[0]})")
        return 0
    try:
        tool_main = load_tool_main()
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 2
    return int(tool_main(argv) or 0)


if __name__ == "__main__":
    sys.exit(main())
