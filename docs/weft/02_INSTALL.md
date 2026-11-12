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

```bash
git clone https://github.com/WeaveMindAI/weft.git ~/weft
git -C ~/weft checkout 61fdacd44b69ef12ca16b30dd533123549e45514     # integrations/weft/WEFT_PIN.json
cd ~/weft && ./setup.sh
weft daemon status
```

Upstream's one-line installer always installs the tip of `main`, so do not use it: it ignores the pin. A checkout that is not the tip of `main` may have no prebuilt binaries, in which case `setup.sh` compiles Weft from source and needs Rust.
`python desk.py weft status` and `python desk.py doctor` compare the checkout's commit with the pin and fail on a
mismatch.

Set `CREDENTIAL_ENCRYPTION_KEY` in Weft's environment before storing any connection.

## 3. Start the DESK node service

```bash
python desk.py weft serve            # 127.0.0.1:14500; prints where the token is
```

Under WSL2 the Weft worker reaches a service on the Windows side only if WSL uses mirrored networking, or if you
start the service with `--host <address>` and pass `--service http://<address>:14500` to `weft run`. Binding to
anything other than loopback exposes the service to that network; the token is then the only guard.

Give Weft the token as a stored connection (`weft connect`, kind "HTTP header key", header
`Authorization: Bearer <token>`) and pick it for the `call` node of each DESK node file a workflow uses. This step
is taken from upstream's documentation and has **not been executed** against a live Weft yet.

## 4. Commands

```bash
python desk.py doctor                              # includes a Weft line
python desk.py weft status                         # runtime, pin match, node service, compiler
python desk.py weft workflows
python desk.py weft nodes                          # which nodes are backed by an engine, which fail closed and why
python desk.py weft validate [<workflow>]          # compile-check with the Weft compiler
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
builds and runs nothing.

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
