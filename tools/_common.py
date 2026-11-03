import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from desk.bridge import ex, guard, load_project, check  # noqa: E402,F401
from desk import spec as S  # noqa: E402,F401
