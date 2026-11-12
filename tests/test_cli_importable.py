"""T-12/T-13/T-19: tools are importable without side effects, typed errors, console entry point, lazy facades."""
import importlib
import importlib.util
import io
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")


def _load(name, path):
    if TOOLS not in sys.path:
        sys.path.insert(0, TOOLS)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ImportableTools(unittest.TestCase):
    def test_desk_py_imports_without_running_and_lists_tools(self):
        mod = _load("desk_tool_under_test", os.path.join(TOOLS, "desk.py"))
        self.assertTrue(callable(mod.main))
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = mod.main(["tools"])
        self.assertEqual(rc, 0)
        self.assertIn("route.py", buf.getvalue())

    def test_desk_py_config_show_and_schema(self):
        mod = _load("desk_tool_under_test2", os.path.join(TOOLS, "desk.py"))
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = mod.main(["config", "schema"])
        self.assertEqual(rc, 0)
        self.assertIn("DESK_MUTATION_POLICY", buf.getvalue())
        buf = io.StringIO()
        with redirect_stdout(buf):
            mod.main(["config", "show", "--json"])
        self.assertIn('"rows"', buf.getvalue())

    def test_desk_py_usage_error_is_typed(self):
        from desk.errors import UsageError, DeskError
        mod = _load("desk_tool_under_test3", os.path.join(TOOLS, "desk.py"))
        with self.assertRaises(UsageError) as cm:
            mod.main(["no-such-subcommand"])
        self.assertIsInstance(cm.exception, DeskError)
        self.assertIsInstance(cm.exception, SystemExit)        # a CLI still exits with the message

    def test_drc_py_imports_without_side_effects(self):
        from desk.errors import UsageError
        mod = _load("drc_tool_under_test", os.path.join(TOOLS, "drc.py"))
        self.assertTrue(callable(mod.main))
        with self.assertRaises(UsageError):
            mod.main([])

    def test_route_pipeline_importable_and_wrapper_is_thin(self):
        from desk.routing import pipeline
        self.assertTrue(callable(pipeline.run))
        self.assertIn("Routing", pipeline.USAGE)
        with open(os.path.join(TOOLS, "route.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertIn("from desk.routing.pipeline import run", src)
        self.assertLess(src.count("\n"), 40)

    def test_subprocess_import_of_tools_has_no_side_effects(self):
        """`python -c "import route"` from tools/ must not touch EasyEDA, read argv or exit."""
        code = "import sys; sys.argv=['x']; import route, drc; print('ok')"
        r = subprocess.run([sys.executable, "-c", code], cwd=TOOLS, capture_output=True, text=True,
                           env={**os.environ, "DESK_TELEMETRY": "0"}, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr[-400:])
        self.assertIn("ok", r.stdout)


class TypedErrors(unittest.TestCase):
    def test_bridge_errors_are_desk_errors_and_system_exits(self):
        from desk import errors, bridge
        for cls in (errors.BridgeUnreachable, errors.BridgeDocumentMismatch, errors.BridgeScriptError,
                    errors.BridgeMutationTimeout, errors.ProjectError, errors.WriteLockHeld,
                    errors.PendingOperationError, errors.ApprovalRequired, errors.UsageError):
            self.assertTrue(issubclass(cls, errors.DeskError))
            self.assertTrue(issubclass(cls, SystemExit))
        self.assertIs(bridge.BridgeMutationTimeout, errors.BridgeMutationTimeout)
        self.assertTrue(errors.BridgeMutationTimeout.possibly_mutated)
        self.assertFalse(errors.BridgeScriptError.possibly_mutated)

    def test_check_raises_script_error_with_context(self):
        from desk.bridge import check
        from desk.errors import BridgeScriptError
        with self.assertRaises(BridgeScriptError) as cm:
            check({"error": "WRONG SHEET", "active": "abc"})
        self.assertEqual(cm.exception.context["result"]["active"], "abc")
        self.assertIn("WRONG SHEET", str(cm.exception))
        self.assertEqual(check({"ok": 1}), {"ok": 1})

    def test_load_project_raises_project_error(self):
        from desk.bridge import load_project
        from desk.errors import ProjectError
        import tempfile
        with self.assertRaises(ProjectError) as cm:
            load_project(tempfile.mkdtemp())
        self.assertTrue(cm.exception.context["path"].endswith("project.json"))

    def test_lock_errors_are_typed(self):
        import tempfile
        from desk import ops
        from desk.errors import WriteLockHeld, PendingOperationError
        d = tempfile.mkdtemp()
        with ops.write_op(d, "build", "A"):
            with self.assertRaises(WriteLockHeld):
                with ops.write_op(d, "build", "B"):
                    pass
        with self.assertRaises(RuntimeError):
            with ops.write_op(d, "build", "C") as r:
                r["dirty"] = True
                raise RuntimeError("bridge timeout")
        with self.assertRaises(PendingOperationError) as cm:
            with ops.write_op(d, "build", "C"):
                pass
        self.assertEqual(cm.exception.context["target"], "C")


class ConsoleEntryPoint(unittest.TestCase):
    def test_version_flag(self):
        from desk import cli
        from desk._version import __version__
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(cli.main(["--version"]), 0)
        self.assertIn(__version__, buf.getvalue())

    def test_delegates_to_tools_desk_main(self):
        from desk import cli
        with mock.patch.object(cli, "load_tool_main", return_value=lambda argv: 7 if argv == ["x"] else 0):
            self.assertEqual(cli.main(["x"]), 7)

    def test_pyproject_declares_script_and_no_dependencies(self):
        with open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8") as f:
            txt = f.read()
        self.assertIn('desk = "desk.cli:main"', txt)
        self.assertIn("dependencies = []", txt)
        self.assertIn('requires-python = ">=3.9"', txt)
        self.assertTrue(os.path.exists(os.path.join(ROOT, ".gitattributes")))
        self.assertTrue(os.path.exists(os.path.join(ROOT, ".github", "workflows", "ci.yml")))


class LazyFacades(unittest.TestCase):
    def test_routing_and_rework_facades_resolve_every_export(self):
        import desk.routing as R
        import desk.rework as W
        for name in R.__all__:
            self.assertTrue(getattr(R, name) is not None, name)
        for name in W.__all__:
            self.assertTrue(getattr(W, name) is not None, name)
        with self.assertRaises(AttributeError):
            R.no_such_thing
        self.assertIn("DSNTree", dir(R))

    def test_facade_import_does_not_load_submodules(self):
        code = ("import sys; import desk.routing; import desk.rework; "
                "print(sum(1 for m in sys.modules if m.startswith('desk.routing.') or m.startswith('desk.rework.')))")
        r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr[-300:])
        self.assertEqual(r.stdout.strip(), "0")

    def test_facade_import_is_cheap(self):
        code = ("import time; t=time.perf_counter(); import desk.routing, desk.rework; "
                "print(round((time.perf_counter()-t)*1000, 1))")
        r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=60)
        ms = float(r.stdout.strip())
        self.assertLess(ms, 60.0, f"facade import took {ms} ms (was 114 / 258 ms before T-19)")


if __name__ == "__main__":
    unittest.main()
