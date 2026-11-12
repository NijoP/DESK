"""`python desk.py weft <command>`: operate the Weft orchestration layer without knowing its internals.

    status                         is Weft installed, which version, does it match the pin, is the node service up
    workflows                      the DESK workflows written in Weft
    nodes [--json]                 the DESK node contracts and which are backed by an engine
    validate [<workflow>]          compile-check a workflow with the Weft compiler (all of them when none is named)
    gen [--check]                  regenerate integrations/weft/nodes/desk/*.weft from the contracts
    serve [--port N]               start the DESK node service Weft calls
    check-run <workflow> [--project <P>] [--requirements <file>] [--evidence <name>]
                                   would Weft admit that run? (Weft's own admission check; runs nothing)
    run <workflow> --project <P> --requirements <file> [--evidence <name>]
                                   start a durable Weft run (needs the Weft runtime and the node service)
    addresses <workflow>           the HttpRequest nodes `weft connect --grant` must give the node-service key to
    signals [--json]               approvals waiting in Weft (needs DESK_WEFT_SIGNAL_TOKEN)
    answer <node> approve|reject|skip
                                   a person's decision on one waiting approval, through Weft's signal API
    history --project <P> [--json] runs recorded for a project: DESK trace, and Weft's own list when it is up
    resume <run-id> [--reseed <workflow>]
                                   where a run stands and what resumes it
    build-validator --checkout <dir> [--apply-windows-shim]
                                   build the compiler harness from a pinned Weft checkout

Exit codes: 0 ok, 1 a check failed, 2 usage, 3 Weft unavailable (there is no fallback orchestrator).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from desk import config as deskcfg
from desk.weft import contracts, runtime as rt, service, staging, weftgen
from desk.weft.store import RecordStore, StoreError


def _flag(a: List[str], name: str, default: Optional[str] = None) -> Optional[str]:
    if name in a:
        i = a.index(name)
        if i + 1 < len(a):
            return a[i + 1]
        raise SystemExit(f"{name} needs a value")
    return default


def _service_url(a: List[str]) -> str:
    return _flag(a, "--service") or os.environ.get("DESK_WEFT_SERVICE_URL") or f"http://127.0.0.1:{service.DEFAULT_PORT}"


def service_health(url: str, timeout: float = 2.0) -> Optional[Dict[str, Any]]:
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/health", timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None


def _project_id(path_or_id: str) -> str:
    return os.path.basename(os.path.normpath(path_or_id))


def _projects_root(path_or_id: str) -> Optional[str]:
    """`projects/<P>` or an absolute project folder names its own root; a bare id uses the default root."""
    norm = os.path.normpath(path_or_id)
    if os.path.dirname(norm):
        return os.path.dirname(os.path.abspath(norm))
    return None


def cmd_status(a: List[str], runtime: rt.WeftRuntime) -> int:
    st = runtime.status()
    url = _service_url(a)
    health = service_health(url)
    h = rt.harness()
    doc = {"weft": st, "nodeService": {"url": url, "up": health is not None, "detail": health},
           "compilerHarness": {"configured": h is not None, "checkout": (h or {}).get("checkout")},
           "nodes": {"declared": len(contracts.CONTRACTS), "available": sum(1 for c in contracts.CONTRACTS if c.status == "available")},
           "workflows": [w["name"] for w in staging.workflows()]}
    if "--json" in a:
        print(json.dumps(doc, indent=2))
    else:
        print(f"Weft pin        {st['pin'][:12]} (changelog {st['pinVersion']})")
        if st["available"]:
            match = {True: "matches the pin", False: "DOES NOT MATCH THE PIN", None: "checkout commit unknown"}[st.get("pinMatch")]
            print(f"Weft runtime    {st['kind']}: {st.get('version') or 'version unknown'}; {match}")
            print(f"Weft daemon     {'running' if st['daemon']['running'] else 'NOT RUNNING'}  {st['daemon']['detail']}")
        else:
            print(f"Weft runtime    NOT INSTALLED ({st['reason']}). Orchestrated workflows cannot run; see docs/weft/02_INSTALL.md")
        print(f"Node service    {'up' if health else 'DOWN'} at {url}" + ("" if health else "  (start it: python desk.py weft serve)"))
        print(f"Compiler check  {'weft validate' if st['available'] else ('compiler harness' if h else 'NONE: build the harness or install Weft')}")
        print(f"DESK nodes      {doc['nodes']['available']} backed by an engine, {doc['nodes']['declared'] - doc['nodes']['available']} declared and failing closed")
        print(f"Workflows       {', '.join(doc['workflows']) or 'none'}")
    return 0 if st["available"] and st.get("pinMatch") is not False else 3


def cmd_workflows(a: List[str]) -> int:
    for w in staging.workflows():
        print(f"{w['name']:28} {w['summary']}")
    return 0


def cmd_nodes(a: List[str]) -> int:
    if "--json" in a:
        print(json.dumps([c.to_dict() for c in contracts.CONTRACTS], indent=2))
        return 0
    for c in contracts.CONTRACTS:
        state = "available  " if c.status == "available" else "UNAVAILABLE"
        print(f"{state} {c.node_id:32} {c.version:7} {c.stage:13} {c.engine}")
        if c.status != "available":
            print(f"            reason: {c.unavailable_reason}")
    return 0


def validate_workflow(name: str, runtime: rt.WeftRuntime) -> Dict[str, Any]:
    staged = staging.stage(name)
    if runtime.available():
        result = runtime.validate(staged, name)
    else:
        h = rt.harness()
        if h is None:
            raise rt.WeftUnavailable("no Weft compiler is available: install Weft, or build the compiler harness with "
                                     "`python desk.py weft build-validator --checkout <pinned weft checkout>`")
        result = rt.harness_validate(staged, h)
    result["workflow"] = name
    return result


def cmd_validate(a: List[str], runtime: rt.WeftRuntime) -> int:
    drift = weftgen.drift()
    if drift:
        print("node files differ from the contracts (run `python desk.py weft gen`): " + ", ".join(drift))
        return 1
    names = [x for x in a if not x.startswith("--")] or [w["name"] for w in staging.workflows()]
    rc = 0
    results = []
    for name in names:
        try:
            r = validate_workflow(name, runtime)
        except KeyError as e:
            print(str(e).strip("'\""))
            return 2
        results.append(r)
        if not r["ok"]:
            rc = 1
    if "--json" in a:
        print(json.dumps(results, indent=2))
        return rc
    for r in results:
        print(f"{r['workflow']}: {'VALID' if r['ok'] else 'INVALID'}  ({r['validator']}, {len(r['errors'])} error(s), {len(r['warnings'])} warning(s))")
        for d in r["errors"]:
            print(f"  error   {d.get('code', '')}: {d.get('message', '')}")
        for d in r["warnings"]:
            print(f"  warning {d.get('code', '')}: {d.get('message', '')}")
    print("A valid graph is an orchestration check only; it does not approve any electrical design.")
    return rc


def cmd_gen(a: List[str]) -> int:
    problems = contracts.all_problems()
    if problems:
        print("\n".join(problems))
        return 1
    if "--check" in a:
        drift = weftgen.drift()
        print("\n".join(drift) if drift else "node files match the contracts")
        return 1 if drift else 0
    print(f"wrote {len(weftgen.write_all())} node files to {os.path.relpath(weftgen.NODES_DIR, staging.REPO)}")
    return 0


def cmd_serve(a: List[str]) -> int:
    from desk.weft import nodes
    port = int(_flag(a, "--port", str(service.DEFAULT_PORT)))
    host = _flag(a, "--host", "127.0.0.1")
    token = service.load_or_create_token()
    provider = nodes.desk_provider()
    server = service.make_server(token, host=host, port=port, projects_root=_flag(a, "--projects-root"), provider=provider)
    print(f"DESK node service on http://{host}:{port}  (token: {'DESK_WEFT_TOKEN' if os.environ.get('DESK_WEFT_TOKEN') else service.token_path()})")
    print(f"model provider: {'configured' if provider else 'none (model nodes answer PROVIDER_UNAVAILABLE)'}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def _positionals(a: List[str]) -> List[str]:
    return [x for i, x in enumerate(a) if not x.startswith("--") and (i == 0 or not a[i - 1].startswith("--"))]


def _run_inputs(url: str, project: str, requirements: str, evidence: Optional[str]) -> Dict[str, str]:
    """The run inputs of a DESK workflow: one `Text` node per input, handed through `weft run --from`."""
    inputs = {"service": url, "projectId": _project_id(project), "requirements": requirements}
    if evidence:
        inputs["evidenceRef"] = evidence
    return inputs


def cmd_check_run(a: List[str], runtime: rt.WeftRuntime) -> int:
    """Would Weft admit the run `desk.py weft run` starts? Judged by Weft itself, or by upstream's code in the harness."""
    names = _positionals(a)
    if not names:
        print("usage: desk.py weft check-run <workflow> [--project <P>] [--requirements <file>] [--evidence <name>]")
        return 2
    name = names[0]
    requirements = "check-run placeholder"
    if _flag(a, "--requirements"):
        with open(_flag(a, "--requirements"), encoding="utf-8") as f:
            requirements = f.read()
    try:
        staged = staging.stage(name)
    except KeyError as e:
        print(str(e).strip("'\""))
        return 2
    inputs = _run_inputs(_service_url(a), _flag(a, "--project") or "check", requirements, _flag(a, "--evidence"))
    if name == "hardware_design" and "evidenceRef" not in inputs:
        inputs["evidenceRef"] = "check"
    if runtime.available():
        r = runtime.check_run(staged, name, inputs)
    else:
        h = rt.harness()
        if h is None:
            raise rt.WeftUnavailable("no Weft run check is available: install Weft, or build the compiler harness with "
                                     "`python desk.py weft build-validator --checkout <pinned weft checkout>`")
        r = rt.harness_check_run(staged, h, rt.run_flags(inputs, durable=True))
    r["workflow"] = name
    if "--json" in a:
        print(json.dumps(r, indent=2))
    else:
        print(f"{name}: {'ADMITTED' if r['ok'] else 'REFUSED'}  ({r['checker']}, {len(r['runs'])} place(s) would run)")
        if r.get("refusal"):
            print("  " + str(r["refusal"]).replace("\n", "\n  "))
        print("Admission means the run could start. It runs nothing and approves no electrical design.")
    return 0 if r["ok"] else 1


def cmd_addresses(a: List[str]) -> int:
    """The HttpRequest places of a workflow, spelled for `weft connect <node> --grant <id>`: each needs the node-service pick."""
    names = _positionals(a)
    if not names:
        print("usage: desk.py weft addresses <workflow> [--json]")
        return 2
    h = rt.harness()
    if h is None:
        raise rt.WeftUnavailable("listing node addresses needs the compiler harness: "
                                 "`python desk.py weft build-validator --checkout <pinned weft checkout>`")
    try:
        r = rt.harness_addresses(staging.stage(names[0]), h)
    except KeyError as e:
        print(str(e).strip("'\""))
        return 2
    if "--json" in a:
        print(json.dumps(r, indent=2))
    elif r["ok"]:
        print("\n".join(r["addresses"]))
    else:
        print(f"could not list the addresses: {r['detail']}")
    return 0 if r["ok"] else 1


SIGNAL_TOKEN_ENV = "DESK_WEFT_SIGNAL_TOKEN"


def _dispatcher(a: List[str]) -> str:
    return _flag(a, "--dispatcher") or deskcfg.get("DESK_WEFT_DISPATCHER") or "http://127.0.0.1:14111"


def _signal_token() -> Optional[str]:
    """The signal token, from desk.config (environment or the user config file; a secret is refused in the repo file).

    Never taken from the command line, where other processes could read it."""
    token = (deskcfg.get(SIGNAL_TOKEN_ENV) or "").strip()
    if not token:
        print(f"set {SIGNAL_TOKEN_ENV} to a Weft signal token (`weft token mint`), in the environment or ~/.desk/config.json")
        return None
    return token


def cmd_signals(a: List[str]) -> int:
    """The approvals waiting in Weft that the signal token can see. Link tokens are never printed."""
    token = _signal_token()
    if token is None:
        return 2
    r = rt.waiting_signals(_dispatcher(a), token)
    shown = [{k: v for k, v in s.items() if k != "token"} for s in r["signals"]]
    if "--json" in a:
        print(json.dumps({"ok": r["ok"], "status": r["status"], "signals": shown}, indent=2))
    elif not r["ok"]:
        print(f"could not list waiting nodes at {_dispatcher(a)} (HTTP {r['status']})")
    else:
        for s in shown:
            print(f"{s.get('nodeId')}  kind={s.get('kind')}  run={s.get('runId', '?')}")
        if not shown:
            print("nothing is waiting")
    return 0 if r["ok"] else 1


def cmd_answer(a: List[str]) -> int:
    """A person's decision on one waiting approval: `answer <node> approve|reject|skip`. Never automatic."""
    pos = _positionals(a)
    if len(pos) != 2 or pos[1] not in rt.DECISIONS:
        print("usage: desk.py weft answer <node, e.g. approve.review> approve|reject|skip [--dispatcher URL]")
        return 2
    token = _signal_token()
    if token is None:
        return 2
    r = rt.answer_signal(_dispatcher(a), token, pos[0], pos[1])
    print(json.dumps(r, indent=2))
    if r["ok"]:
        print("Weft resumes the run by itself. DESK records the decision only when its approval node runs.")
    return 0 if r["ok"] else 1


def cmd_run(a: List[str], runtime: rt.WeftRuntime) -> int:
    names = _positionals(a)
    project, req_file = _flag(a, "--project"), _flag(a, "--requirements")
    if not names or not project or not req_file:
        print("usage: desk.py weft run <workflow> --project <P> --requirements <file> [--evidence <name>]")
        return 2
    runtime.require()
    url = _service_url(a)
    if service_health(url) is None:
        print(f"the DESK node service is not answering at {url}; start it with `python desk.py weft serve`")
        return 1
    v = validate_workflow(names[0], runtime)
    if not v["ok"]:
        print(f"{names[0]} does not compile; run `python desk.py weft validate {names[0]}`")
        return 1
    with open(req_file, encoding="utf-8") as f:
        requirements = f.read()
    inputs = _run_inputs(url, project, requirements, _flag(a, "--evidence"))
    r = runtime.run(staging.stage(names[0]), names[0], inputs, durable=True)
    print(json.dumps(r, indent=2))
    return 0 if r["ok"] else 1


def cmd_history(a: List[str], runtime: rt.WeftRuntime) -> int:
    project = _flag(a, "--project")
    if not project:
        print("usage: desk.py weft history --project <P> [--json]")
        return 2
    try:
        store = RecordStore(_project_id(project), _projects_root(project))
    except StoreError as e:
        print(e.message)
        return 1
    doc: Dict[str, Any] = {"project": store.project_id, "deskTrace": store.list_runs(), "weft": None}
    if runtime.available():
        doc["weft"] = runtime.runs(tag=store.project_id)
    if "--json" in a:
        print(json.dumps(doc, indent=2))
        return 0
    if not doc["deskTrace"]:
        print(f"no Weft run has called a DESK node for project {store.project_id}")
    for r in doc["deskTrace"]:
        print(f"{r['runId']:40} calls={r['calls']:<3} last={r['lastNode']}  failed={r['failed'] or '-'}  blocked={r['blocked'] or '-'}")
    print("Weft's own run list: " + ("see --json" if doc["weft"] else "unavailable (Weft is not installed)"))
    return 0


def cmd_resume(a: List[str], runtime: rt.WeftRuntime) -> int:
    ids = [x for i, x in enumerate(a) if not x.startswith("--") and (i == 0 or not a[i - 1].startswith("--"))]
    if not ids:
        print("usage: desk.py weft resume <run-id> [--reseed <workflow>]")
        return 2
    runtime.require()
    state = runtime.run_state(ids[0])
    print(json.dumps(state, indent=2))
    if state["state"] == "waiting_for_input":
        print("The run is paused on a human approval. Answer it in the Weft tasks extension; Weft resumes it by itself.")
    elif state["state"] == "still_running":
        print("The run is still executing; nothing to resume.")
    elif state["state"] == "failed_or_cancelled":
        wf = _flag(a, "--reseed")
        if not wf:
            print("Weft cannot restart a failed run in place. `--reseed <workflow>` starts a new run that reuses its completed nodes;")
            print("DESK nodes replay their stored results, so no engine work is repeated. A live board change is never rolled back by this.")
            return 1
        r = runtime.reseed(staging.stage(wf), wf, ids[0])
        print(json.dumps(r, indent=2))
        return 0 if r["ok"] else 1
    return 0


_SHIM_OLD_A = "    use std::os::unix::fs::OpenOptionsExt as _;\n    std::fs::create_dir_all(dir)?;"
_SHIM_NEW_A = "    #[cfg(unix)]\n    use std::os::unix::fs::OpenOptionsExt as _;\n    #[cfg(not(unix))]\n    let _ = mode;\n    std::fs::create_dir_all(dir)?;"
_SHIM_OLD_B = "    let written = std::fs::OpenOptions::new()\n        .write(true)\n        .create_new(true)\n        .mode(mode)\n        .open(&partial)"
_SHIM_NEW_B = "    let mut options = std::fs::OpenOptions::new();\n    options.write(true).create_new(true);\n    #[cfg(unix)]\n    options.mode(mode);\n    let written = options\n        .open(&partial)"


def cmd_build_validator(a: List[str]) -> int:
    checkout = _flag(a, "--checkout")
    if not checkout or not os.path.isdir(os.path.join(checkout, "crates", "weft-compiler")):
        print("usage: desk.py weft build-validator --checkout <weft checkout> [--apply-windows-shim]")
        return 2
    checkout = os.path.abspath(checkout).replace("\\", "/")
    pin = staging.pin()["commit"]
    head = subprocess.run(["git", "-C", checkout, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    if head != pin:
        print(f"the checkout is at {head or 'an unknown commit'}, the pin is {pin}; check out the pin first")
        return 1
    if sys.platform.startswith("win"):
        target = os.path.join(checkout, "crates", "weft-core", "src", "infra", "install.rs")
        with open(target, encoding="utf-8") as f:
            src = f.read()
        if _SHIM_OLD_A in src:
            if "--apply-windows-shim" not in a:
                print("weft-core does not compile on Windows: one install-file writer (infra/install.rs write_whole) uses Unix-only")
                print("file modes. Re-run with --apply-windows-shim to gate those two lines in THIS checkout (use a scratch")
                print("checkout, not a Weft install). The compiler itself is not touched.")
                return 1
            if src.count(_SHIM_OLD_A) != 1 or src.count(_SHIM_OLD_B) != 1:
                print("the shim does not apply cleanly to this checkout; refusing to guess")
                return 1
            with open(target, "w", encoding="utf-8", newline="\n") as f:
                f.write(src.replace(_SHIM_OLD_A, _SHIM_NEW_A).replace(_SHIM_OLD_B, _SHIM_NEW_B))
            print("applied the Windows shim to crates/weft-core/src/infra/install.rs")
    out = os.path.join(staging.BUILD_DIR, "validator")
    os.makedirs(os.path.join(out, "src"), exist_ok=True)
    tpl = os.path.join(staging.WEFT_DIR, "validator")
    for src_name, dst in (("Cargo.toml.in", os.path.join(out, "Cargo.toml")), ("main.rs.in", os.path.join(out, "src", "main.rs"))):
        with open(os.path.join(tpl, src_name), encoding="utf-8") as f:
            text = f.read().replace("@CHECKOUT@", checkout)
        with open(dst, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    shutil.copyfile(os.path.join(checkout, "Cargo.lock"), os.path.join(out, "Cargo.lock"))
    # rustup picks the toolchain from the folder cargo runs in. Upstream installs rustup with no default toolchain
    # and lets its rust-toolchain.toml choose, so the harness carries the same file or cargo has no toolchain.
    toolchain = os.path.join(checkout, "rust-toolchain.toml")
    if os.path.isfile(toolchain):
        shutil.copyfile(toolchain, os.path.join(out, "rust-toolchain.toml"))
    with open(os.path.join(out, "CHECKOUT"), "w", encoding="utf-8") as f:
        f.write(checkout)
    cargo = shutil.which("cargo")
    if not cargo:
        print("cargo is not on PATH; install Rust (rustup) and re-run")
        return 1
    rc = subprocess.run([cargo, "build", "--release"], cwd=out).returncode
    print("compiler harness built" if rc == 0 else "cargo build failed (on Windows the GNU toolchain needs MinGW binutils on PATH)")
    return 0 if rc == 0 else 1


def main(argv: List[str], runtime: Optional[rt.WeftRuntime] = None) -> int:
    runtime = runtime or rt.WeftRuntime()
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0 if argv else 2
    cmd, a = argv[0], argv[1:]
    try:
        if cmd == "status":
            return cmd_status(a, runtime)
        if cmd == "workflows":
            return cmd_workflows(a)
        if cmd == "nodes":
            return cmd_nodes(a)
        if cmd == "validate":
            return cmd_validate(a, runtime)
        if cmd == "gen":
            return cmd_gen(a)
        if cmd == "serve":
            return cmd_serve(a)
        if cmd == "check-run":
            return cmd_check_run(a, runtime)
        if cmd == "addresses":
            return cmd_addresses(a)
        if cmd == "signals":
            return cmd_signals(a)
        if cmd == "answer":
            return cmd_answer(a)
        if cmd == "run":
            return cmd_run(a, runtime)
        if cmd == "history":
            return cmd_history(a, runtime)
        if cmd == "resume":
            return cmd_resume(a, runtime)
        if cmd == "build-validator":
            return cmd_build_validator(a)
    except rt.WeftUnavailable as e:
        print(str(e))
        return 3
    print(__doc__)
    return 2
