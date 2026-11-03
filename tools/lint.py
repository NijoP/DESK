"""Offline gate (no EasyEDA). Must print PASS before tools/build.py is allowed.
Usage: python tools/lint.py projects/<product> [BLOCK_ID] [--final]"""
import sys
from _common import S

args = [a for a in sys.argv[1:] if not a.startswith("--")]
E, W = S.lint(args[0], args[1] if len(args) > 1 else None, final="--final" in sys.argv)
for w in W: print("WARN ", w)
for e in E: print("ERROR", e)
print("PASS" if not E else f"FAIL ({len(E)} errors)")
sys.exit(1 if E else 0)
