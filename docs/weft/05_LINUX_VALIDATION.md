# DESK × Weft: Linux validation procedure

For the separate Linux machine. **Nothing here has been run yet.** The scripts are written against the pinned
upstream source (`61fdacd44b69ef12ca16b30dd533123549e45514`) and parse-checked; their DESK-side checks are unit
tested on Windows (`tests/test_weft_linux_package.py`). Running this procedure is what turns the "not executed"
rows of [04_STATUS.md](04_STATUS.md) into results.

Scripts: `integrations/weft/linux/`. Every step appends `PASS`, `FAIL`, `NOT RUN` or `BLOCKED` lines to
`~/desk-weft-validation/results.tsv`. A step never writes `PASS` without the evidence it names.

## 1. Machine

| | Needed |
|---|---|
| OS | Ubuntu 24.04 LTS, x86_64 or aarch64 (upstream publishes these two Linux targets). Another distribution works if you install the same packages by hand |
| Disk | about 40 GB free in `$HOME` (Weft compiles from source; Docker images; BuildKit cache capped at 20 GB by upstream) |
| Memory | 8 GB or more; less works but the Rust build is slow |
| Network | GitHub, Docker Hub / Docker's apt repository, crates.io, static.rust-lang.org |
| Exclusive | **A machine whose Docker holds nothing you need.** Upstream's installer reaps orphaned anonymous Docker volumes and old Weft images on every install (see step 2) |

Do not use a machine with a Weft install of its own: step 2 installs the **default** Weft install.

## 2. Procedure

```bash
git clone https://github.com/NijoP/DESK.git ~/DESK && cd ~/DESK
git checkout <the DESK commit under test>
L=integrations/weft/linux

bash $L/00_preflight.sh                       # read-only
bash $L/10_install_prereqs.sh --yes           # apt, Docker Engine, rustup (sudo); then log out and in again
bash $L/00_preflight.sh                       # must pass now
bash $L/20_install_weft.sh --yes              # pinned Weft, from source (tens of minutes)
bash $L/30_prepare_desk.sh                    # harness, validate, run check, node service, connection picks
bash $L/40_run_requirement_to_profile.sh      # park, restart survival, approve, replay, reject
bash $L/50_run_hardware_design.sh             # fail-closed at the first unwired stage, seeded re-run
bash $L/60_full_suite.sh                      # the whole DESK suite on Linux, with Weft present
bash $L/90_collect.sh                         # diagnostics bundle (secrets excluded and checked)
bash $L/99_cleanup.sh                         # stop the service and runs, revoke the signal token
```

Environment knobs (all optional): `WEFT_DIR` (default `~/weft`), `DESK_VALIDATION_DIR` (default
`~/desk-weft-validation`), `DESK_VALIDATION_PROJECT` (default `WEFTVAL01`), `DESK_WEFT_SERVICE_PORT` (default
14500), `DESK_WEFT_DISPATCHER` (default `http://127.0.0.1:14111`), `DESK_WEFT_CONNECTION_ID` (reuse a stored
connection).

### Step 1: prerequisites (`10_install_prereqs.sh --yes`)

Installs `git curl ca-certificates build-essential pkg-config python3`, Docker Engine from Docker's own apt
repository, and rustup **with no default toolchain**, which is how upstream installs it: Weft's
`rust-toolchain.toml` selects Rust 1.99.1 at the pin. The C compiler is needed by `ring` and `zstd-sys` in Weft's
dependency tree. It enables lingering so Weft's `systemd --user` service survives logout. Rustup itself and
Docker are their publishers' current releases; everything Weft builds is pinned.

### Step 2: pinned Weft (`20_install_weft.sh --yes`)

What the script does and why, from the pinned source:

| Fact | Source at the pin |
|---|---|
| A checkout's branch picks the install; a detached HEAD picks none and is refused | `crates/weft-core/src/infra/install.rs` (`for_branch`, `on_no_branch`) |
| `WEFT_INSTALL=default` names the default install, whose `weft` is linked into `~/.local/bin` | same file; `setup.sh` (`resolve_install`, `on_default_install`) |
| Prebuilt binaries exist only for the tree CI last published, so the pin builds from source | `setup.sh` (`decide_prebuilt_use`) |
| `--cli --daemon` skips the VS Code and browser extensions (no Node or pnpm needed) | `setup.sh` header |
| Every install reaps orphaned anonymous Docker volumes (`docker volume prune --force`, engine ≥ 23 only), caps BuildKit at 20 GB, removes unused Weft images | `setup.sh` ("Disk hygiene") |
| `CREDENTIAL_ENCRYPTION_KEY` is read from the shell that starts the daemon and kept in the install's secrets file; without it a public development key seals stored credentials | `crates/weft-cli/src/commands/daemon.rs` (`secrets`), `docs/src/connections/how-they-work.md` |

The script refuses a modified Weft checkout, generates the encryption key into
`~/desk-weft-validation/secrets/` (mode 600), and checks `weft daemon status` and DESK's pin match.

### Step 3: DESK against Weft (`30_prepare_desk.sh`)

1. Builds the compiler harness (now with the checkout's `rust-toolchain.toml`, without which a rustup that has no
   default toolchain cannot build it).
2. `weft validate` on both workflows; `weft run --check` with exactly the flags `desk.py weft run` will pass.
3. Creates the scratch project `WEFTVAL01` and starts the DESK node service on `127.0.0.1:14500` with a fresh token;
   checks a call without the token gets 401.
4. Stores the token in Weft once and picks it for **every** DESK `HttpRequest`. The facts behind this:
   - `HttpRequest.connection` is an optional `Access[http_header_key]` input. Left unpicked, the call goes out
     with no header, the service answers 401, and the run fails closed. It does not fail open.
     Source: `catalog/http/request/metadata.json`.
   - A pick belongs to one node at one include site and is kept by the install, never in a `.weft` file.
     Source: `docs/src/build/connections.md`.
   - `weft connect <node> --door own --set header=Authorization --set-env value=<VAR>` creates the connection
     without putting the secret on a command line.
   - `weft --json connect <node> --grant <id>` picks it for another node.
     Source: `crates/weft-cli/src/commands/connect.rs`.
   - The node names come from `desk.py weft addresses <workflow>`, which uses upstream's own `address_of` through
     the harness: 7 sites for `requirement_to_profile`, 32 for `hardware_design`.

### Step 4: `requirement_to_profile` (`40_run_requirement_to_profile.sh`)

| Check | Expected | How it is read |
|---|---|---|
| Run starts, durable | a run id | `weft --json run --detach --durable`, NDJSON `detail.runId` (`crates/weft-cli/src/progress.rs`) |
| Parks on the profile approval | `weft wait --waiting-for-input` exit 11; `weft node-state <run> approve.review` waiting | Weft |
| Six DESK engines ran, no approval yet | intake, validator, classifier, profile compiler, families, power | DESK trace (`check_trace.py`) |
| **Survives a runtime restart** | after `weft daemon stop` / `start`, still exit 11 | Weft |
| Approve through the signal API | `POST /signal/<link>` `{"decision": "approve"}` accepted | `desk.py weft answer`; routes from `crates/weft-dispatcher/src/api/mod.rs`, client shape from upstream's own `crates/weft-e2e/src/human.rs` |
| Resumes and completes | `weft wait` exit 0; timing recorded | Weft |
| DESK recorded the decision | a `profile` approval, `approved`, bound to the profile hash; every DESK call passed | DESK records |
| Second identical run | all six engines **replayed** from DESK's stored results | DESK trace (`replayed: true`) |
| Rejection | a `profile` approval recorded as `rejected` | DESK records |

The approval subject is the validation fixture, not a client design. The signal token is minted with
`--tags WEFTVAL01 --expires 12h`, kept in a mode-600 file, and passed to DESK only through
`DESK_WEFT_SIGNAL_TOKEN`; DESK never prints it or the per-node link tokens.

### Step 5: `hardware_design` (`50_run_hardware_design.sh`)

Expected to **fail closed**. `DeskComponentSearch` is declared but has no engine adapter yet. The node service
answers it with HTTP 501 `NODE_UNAVAILABLE` and no `outputs`. `HttpRequest` treats an error status as a
successful call, so the stop has to come from the next node: the typed `Cast` should fail, and the run should
end **failed**. The script checks:

- `weft wait` gives exit 10;
- the understand stage and component families ran;
- `DeskComponentSearch` failed with `NODE_UNAVAILABLE`;
- nothing after it ran (no MPN resolution, BOM, schematic, placement, routing, quality gate or release);
- no approval was recorded.

It then starts a seeded re-run (`weft run --seed=<failed run>`). The re-run must stop at the same place, and
DESK must see no repeat of the understand stage.

If the run ends **completed** or **parked**, that is a fail-open defect in the workflow design. Stop and report it.

### Step 6: suite (`60_full_suite.sh`)

The whole DESK suite, with the model-provider variables cleared for the run. The Weft tests that skip on a
machine with no compiler run here. The routing-engine test needs a Freerouting jar and Java 25
(`FREEROUTING_JAR`, `DESK_JAVA`); if it fails for that reason, record it as BLOCKED, not as passed.

## 3. Failure diagnosis

| Symptom | Look at | Usual cause |
|---|---|---|
| `setup.sh failed` | `logs/setup.log`, `~/.local/share/weft/setup-runs.log` | Docker unreachable (re-login after joining the group), out of disk, no C compiler |
| `weft daemon` not running | `weft daemon logs` | Postgres container did not start; port 14111 in use |
| `pinMatch` not True | `git -C ~/weft rev-parse HEAD` | Checkout moved off the pin |
| validate FAIL | `logs/validate.<wf>.json` | Upstream compiler differs from the harness: compare both outputs, report |
| check-run FAIL | `logs/check-run.<wf>.log` | A run input is not a `Text` node the program has |
| connect FAIL | `logs/connect.create.log` | Credential field names differ; `weft connect <node>` on a terminal lists them |
| Run never parks (`weft wait` 10) | `weft logs <run>`, `desk.py weft history --project ... --json` | A DESK call got 401 (a pick missing: rerun step 3) or 4xx (contract mismatch) |
| Answer finds 0 nodes | `logs/signals_A.txt` | The listed node id is spelled differently from `approve.review`; the token's tag scope did not match the run |
| Answer finds 2+ nodes | `logs/signals_A.txt` | Another run is parked; stop it (`weft stop <run>`) |
| Restart loses the run | `weft runs --tag WEFTVAL01` | Durability not in effect: report with the bundle |
| `hardware_design` completes or parks | `logs/hd_trace.json`, `logs/hd_run.log` | Fail-open path in the graph: stop, report |

Always finish with `90_collect.sh`. It bundles the results, logs, DESK records and Weft's run list and version.
It leaves out the secrets folder, and it deletes the bundle if any secret value appears in it.

## 4. Cleanup

`99_cleanup.sh` by default:

- stops the DESK node service;
- stops the scratch project's unfinished runs;
- revokes the signal token.

Optional flags:

| Flag | What it also does |
|---|---|
| `--forget-connection` | deletes the stored node-service connection |
| `--remove-scratch` | deletes `~/desk-weft-validation` |
| `--uninstall-weft` | runs upstream's `./setup.sh --uninstall` |

It never removes Docker, rustup or apt packages.

## 5. Reporting back

Return `results.tsv` and the bundle. Every row is one of PASS, FAIL, NOT RUN or BLOCKED, and only a PASS backed
by the run's own evidence moves a row of [04_STATUS.md](04_STATUS.md) from "not executed" to "executed".
