"""F-04 regression guard: DESK code never names a real project as a default target.

A project is always explicit (argument, --project, DESK_PROJECT or project.json binding). The only
permitted mention is prose in a docstring that cites where real-board validation came from.
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATTERN = re.compile(r"projects[\\/](WATCH|LIGHT)")
ALLOWED_PROSE = {
    "desk/routing/fixtures.py",            # docstring: where real-board validation results came from
}


def _files():
    for base in ("desk", "tools"):
        for dp, dn, fn in os.walk(os.path.join(ROOT, base)):
            dn[:] = [d for d in dn if d != "__pycache__"]
            for f in fn:
                if f.endswith((".py", ".html", ".js")):
                    yield os.path.join(dp, f)


class NoDefaultProjectTests(unittest.TestCase):
    def test_no_code_names_a_live_project(self):
        offenders = []
        for p in _files():
            rel = os.path.relpath(p, ROOT).replace("\\", "/")
            with open(p, encoding="utf-8", errors="replace") as fh:
                for i, line in enumerate(fh, 1):
                    if PATTERN.search(line) and rel not in ALLOWED_PROSE:
                        offenders.append(f"{rel}:{i}: {line.strip()[:90]}")
        self.assertEqual(offenders, [], "\n".join(offenders))

    def test_projection_default_is_unbound_or_env(self):
        from desk.runtime.projection import ExecutionProjection
        old = os.environ.pop("DESK_PROJECT", None)
        try:
            self.assertEqual(ExecutionProjection().project_id, "")
            os.environ["DESK_PROJECT"] = "projects/EXAMPLE"
            self.assertEqual(ExecutionProjection().project_id, "projects/EXAMPLE")
        finally:
            os.environ.pop("DESK_PROJECT", None)
            if old is not None:
                os.environ["DESK_PROJECT"] = old

    def test_unbound_projection_state_file_stays_out_of_repo(self):
        from desk.runtime.projection import ExecutionProjection
        old = os.environ.pop("DESK_PROJECT", None)
        try:
            path = ExecutionProjection()._state_file_path()
        finally:
            if old is not None:
                os.environ["DESK_PROJECT"] = old
        self.assertFalse(os.path.abspath(path).startswith(ROOT), path)


if __name__ == "__main__":
    unittest.main()
