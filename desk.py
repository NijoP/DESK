#!/usr/bin/env python3
"""
DESK CLI Root Entry Point.
Delegates to tools/desk.py.
"""
import os
import subprocess
import sys

here = os.path.dirname(os.path.abspath(__file__))
desk_tool = os.path.join(here, "tools", "desk.py")

if __name__ == "__main__":
    cmd = [sys.executable, desk_tool] + sys.argv[1:]
    sys.exit(subprocess.call(cmd))
