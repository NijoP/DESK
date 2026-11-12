"""Bind (or re-bind) a project to the ONE EasyEDA Pro window that hosts its project uuid.

Usage:
  python tools/rebind.py projects/<P>            # discover windows, match project_uuid, store window_id in project.json
  python tools/rebind.py projects/<P> --dry      # report only, change nothing
  python tools/rebind.py --list                  # every connected window with its project and active document

Rules (desk/reliability/project_isolation.py):
* identity = project uuid from project.json (fallback: the bound document uuids); never the active window, never a name;
* exactly one matching window binds; zero or several is a refusal (exit 1) and nothing is written;
* read-only towards EasyEDA (two getter calls per window).
Window ids rotate on every gateway reconnect (UPS_1000 F-002, INC-20261112-013); rerun this after a reconnect.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from desk.bridge import GatewayHTTP, SessionRegistry, _persist_window_id  # noqa: E402
from desk.errors import IdentityUnverified, UsageError  # noqa: E402
from desk.reliability.project_isolation import SessionResolver, session_from_project  # noqa: E402


def main(argv):
    args = list(argv)
    if not args:
        raise UsageError(__doc__)
    port = SessionRegistry.get_port()
    resolver = SessionResolver(GatewayHTTP(port))
    if args[0] == "--list":
        wins = resolver.discover()
        for w in wins:
            print(json.dumps({"window_id": w.window_id, "project_uuid": w.project_uuid, "project_name": w.project_name,
                              "document_uuid": w.document_uuid, "document_type": w.document_type, "reachable": w.reachable,
                              "error": w.error}, ensure_ascii=False))
        print(f"{len([w for w in wins if w.window_id])} window(s) on port {port}")
        return 0
    proj = args[0]
    dry = "--dry" in args
    pj = os.path.join(proj, "project.json")
    if not os.path.exists(pj):
        raise UsageError(f"missing {pj}")
    with open(pj, encoding="utf-8") as f:
        info = json.load(f)
    session = session_from_project(proj, info, endpoint=f"http://127.0.0.1:{port}")
    old = session.window_id
    wins = resolver.discover()
    try:
        resolver.resolve(session, wins)
    except IdentityUnverified as e:
        print(str(e))
        return 1
    if session.window_id == old:
        print(f"BOUND {session.window_id} (unchanged) project_uuid={session.project_uuid} document={session.bound_document_uuid or '?'}")
        return 0
    if dry:
        print(f"WOULD REBIND {old} -> {session.window_id} (project_uuid {session.project_uuid}); --dry, nothing written")
        return 0
    _persist_window_id(proj, info, session.window_id or "")
    print(f"REBOUND {old} -> {session.window_id} (project_uuid {session.project_uuid}, generation {session.window_generation}); "
          f"project.json updated")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
