# DESK × Weft: installation and operation

DESK never installs or updates Weft by itself. The steps below are yours to run.

## 1. What you need

| | Linux / macOS | Windows |
|---|---|---|
| Weft runtime | native | inside **WSL2** (upstream has no Windows build) |
| Docker | required by Weft (its Postgres and file store) | Docker Engine inside the WSL distribution, or Docker Desktop |
| Rust | needed when a project has nodes of its own | same, inside WSL |
| DESK | Python 3.11+, no packages | same, on Windows |

## 2. Install the pinned Weft

On Linux, use the scripted procedure: [05_LINUX_VALIDATION.md](05_LINUX_VALIDATION.md)
(`integrations/weft/linux/20_install_weft.sh`). By hand, it amounts to:

```bash
git clone https://github.com/WeaveMindAI/weft.git ~/weft
git -C ~/weft checkout --detach 61fdacd44b69ef12ca16b30dd533123549e45514   # integrations/weft/WEFT_PIN.json
export WEFT_INSTALL=default                       # a detached HEAD picks no install; name the default one
export CREDENTIAL_ENCRYPTION_KEY="$(openssl rand -base64 32)"   # keep it: rows sealed with it open under no other
cd ~/weft && ./setup.sh --cli --daemon --yes
weft daemon status
```

- Upstream's one-line installer always installs the tip of `main`, so do not use it: it ignores the pin.
- The pin is older than what CI last published, so `setup.sh` compiles Weft from source and needs Rust. Install
  rustup with no default toolchain; the checkout's `rust-toolchain.toml` picks Rust 1.99.1.
- A checkout's **branch** picks which Weft install it drives (`crates/weft-core/src/infra/install.rs`). A detached
  HEAD is refused unless `WEFT_INSTALL` names one, so keep `WEFT_INSTALL=default` set in the shell that drives
  DESK's Weft commands. An earlier version of this page said only `git checkout <pin>`, which leaves the checkout
  detached and makes `setup.sh` stop.
- `setup.sh` reaps orphaned anonymous Docker volumes and unused Weft images on every install. Use a machine whose
  Docker holds nothing you need.
- `python desk.py weft status` and `python desk.py doctor` compare the checkout's commit with the pin and fail on a
  mismatch.

## 3. Start the DESK node service

```bash
python desk.py weft serve            # 127.0.0.1:14500; prints where the token is
```

Under WSL2 the Weft worker reaches a service on the Windows side only if WSL uses mirrored networking, or if you
start the service with `--host <address>` and pass `--service http://<address>:14500` to `weft run`. Binding to
anything other than loopback exposes the service to that network; the token is then the only guard.

Give Weft the token as a stored connection and pick it for every DESK call. A pick belongs to one node at one
include site, so `requirement_to_profile` needs 7 picks and `hardware_design` 32. `python desk.py weft addresses
<workflow>` lists them, spelled the way `weft connect` takes them:

```bash
cd .desk_weft/stage/<workflow>
DESK_WEFT_BEARER="Bearer <token>" weft connect <first address> --door own \
    --set header=Authorization --set-env value=DESK_WEFT_BEARER --label desk-node-service
id=$(weft --json connect <first address> --list | python3 -c 'import json,sys; print(json.load(sys.stdin)["picked"])')
for a in $(python desk.py weft addresses <workflow>); do weft --json connect "$a" --grant "$id"; done
```

An unpicked DESK call goes out with no `Authorization` header. The node service answers 401 and the run fails
closed. These commands come from the pinned source (`crates/weft-cli/src/commands/connect.rs`) and
`30_prepare_desk.sh` scripts them. They have **not been executed** against a live Weft yet.

## 4. Commands

```bash
python desk.py doctor                              # includes a Weft line
python desk.py weft status                         # runtime, pin match, node service, compiler
python desk.py weft workflows
python desk.py weft nodes                          # which nodes are backed by an engine, which fail closed and why
python desk.py weft validate [<workflow>]          # compile-check with the Weft compiler
python desk.py weft check-run <workflow>           # would Weft admit the run? (Weft's own admission check)
python desk.py weft addresses <workflow>           # the DESK calls `weft connect --grant` must cover
python desk.py weft signals                        # approvals waiting (DESK_WEFT_SIGNAL_TOKEN in the environment)
python desk.py weft answer approve.review approve  # a person's decision on one waiting approval
python desk.py weft run hardware_design --project projects/<P> --requirements requirements.json [--evidence <name>]
python desk.py weft history --project projects/<P>
python desk.py weft resume <run-id> [--reseed <workflow>]
python desk.py weft gen [--check]                  # regenerate node files after editing desk/weft/contracts.py
```

Requirements may be free text or a JSON object. Declared rails and current limits come only from the JSON form
(`{"text": "...", "voltage_rails": {...}, "current_limits_A": {...}}`); DESK does not size a trace for a current
nobody declared.

`weft resume` is not upstream's vocabulary: Weft resumes a paused run by itself when the answer arrives. The DESK
command reports the run's state and, for a failed run, can start a seeded re-run.

Answering an approval: in upstream's **Weft tasks** browser extension, or headless with `desk.py weft answer`.
The headless path mints a signal token (`weft token mint --tags <project> --expires 12h`) and lists what is waiting
(`GET /signal-token/signals`, Bearer token). It then posts the decision to that node's link
(`POST /signal/<link>` with `{"decision": "approve"}` or `"reject"`, or `/skip`). The routes are in
`crates/weft-dispatcher/src/api/mod.rs`, and upstream's own headless test client does the same
(`crates/weft-e2e/src/human.rs`). DESK answers only the one node named and refuses when zero or several match.
A skipped approval closes its outputs, so everything after it is skipped and no approval is recorded.

## 5. Compile-checking without a Weft runtime

`python desk.py weft validate` uses `weft validate` when Weft is installed. Without it, DESK can still run
upstream's compiler through a small harness:

```bash
git clone https://github.com/WeaveMindAI/weft.git <scratch>/weft
git -C <scratch>/weft checkout 61fdacd44b69ef12ca16b30dd533123549e45514
python desk.py weft build-validator --checkout <scratch>/weft           # add --apply-windows-shim on Windows
python desk.py weft validate
```

The harness (`integrations/weft/validator/`) links upstream's `weft-compiler` and `weft-core` and compiles
upstream's catalog loader unmodified, so a program goes through the same parse, enrich and validate pipeline. It
builds and runs nothing. It has three modes:

| Mode | What it calls upstream | Used by |
|---|---|---|
| validate | `compile_strict`, runtime mode | `desk.py weft validate` |
| `check-run` | `run_spec::judge::judge`, the admission check behind `weft run --check` and the dispatcher | `desk.py weft check-run` |
| `addresses` | `project::address_of`, how `weft connect` spells a node | `desk.py weft addresses` |

It is built with the checkout's own `rust-toolchain.toml` (Rust 1.99.1 at the pin).

Upstream's admission check refuses an unknown start node and a value that is not JSON. It **does not** refuse an
unknown port name. That the run inputs' `value` port is right is therefore checked against upstream's `Text`
metadata (`catalog/basic/text/metadata.json`) by `tests/test_weft_service_runtime.py`.

On Windows:

- `weft-core` does not compile as shipped: one install-file writer (`infra/install.rs`, `write_whole`) uses
  Unix-only file modes. `--apply-windows-shim` gates those two lines in the checkout you name. Use a scratch
  checkout. The compiler is not touched.
- One upstream file (`crates/weft-task-store/tests/db/nul.rs`) cannot be checked out on Windows; git reports it
  and the rest of the tree is usable.
- Rust's GNU toolchain needs MinGW binutils (`as`, `dlltool`) on `PATH`.

The harness is a check, not the reference: it proves the program compiles, not that it runs.

## 6. Updating the pin

1. Read upstream's `CHANGELOG.md` between the two commits.
2. Change `integrations/weft/WEFT_PIN.json`, rebuild the harness, run `python desk.py weft validate`.
3. Run the full test suite.
4. On the Weft machine: `weft maintenance on`, check out the new commit, `./setup.sh`, `weft maintenance off`.
