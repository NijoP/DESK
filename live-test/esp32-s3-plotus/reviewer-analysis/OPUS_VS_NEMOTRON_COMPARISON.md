# Opus 5.5 vs Nemotron 3 Ultra - comparison (independent)
Written 2026-11-12 ~06:42 +05:30 by plotus-sonnet-examiner.

## What the record of the Nemotron run actually contains (read-only inspection)
- Folder `C:\nemotron test\ESP32 S3 development\`: REQUIREMENTS.md, requirements/{DESIGN_PARAMETERS, ACCEPTANCE_CRITERIA, ENGINEERING_ASSUMPTIONS}.md, PROJECT_STATUS.md ("Environment Validation & Requirements Setup", engineering timer "Not started"), and an evaluation/ folder of templates (all TBD) written at 03:18-03:20. schematic, pcb, libraries, manufacturing, tests, logs, benchmarks, failures and reports contain 0 files. The evaluation CSV has exactly 1 row (03:18:00Z); the only 10-minute report is report 001 (pre-engineering). Last file written 03:20:15.
- `NVIDIA_MODEL_DIAGNOSTIC_REPORT.md` (written 02:59, by another model) documents client/config problems making Nemotron unusable at first (reasoning exhausted the output budget; DESK not routed to NVIDIA; Pi/OpenCode config issues; PiAdapter JSONL bug) and the repairs. It says nothing about a board.
- Requirements and acceptance files: SHA-256 of REQUIREMENTS.md, DESIGN_PARAMETERS.md and ACCEPTANCE_CRITERIA.md are identical to the Plotus (Opus) copies (3fabd342..., c1e9fb43..., a40d8bb7...), per FROZEN_HASHES.txt and my own recomputation. So the requirement text is equivalent.
- I found NO evidence in the Nemotron folder that an engineering clock was started or that any stage was attempted. I did not find a timing file for it. Whether a Nemotron attempt was made elsewhere (for example under C:\sensor patch) is outside what I was asked/allowed to inspect, so I make no claim beyond "no engineering artifacts on record in its project folder".

## Consequence
Almost every dimension cannot be compared because the Nemotron side has no artifacts, no timing, no failure register and no telemetry. I do not turn absence of evidence into a score for Nemotron, and I do not declare a winner. Start conditions also differ: different DESK path (C:\sensor patch\DESK vs the Plotus copy), a different EasyEDA window id, an examiner telemetry file with a different schema (10 columns, 1 row) and a model reachable only through a separately repaired NVIDIA endpoint.

## Dimension table
| Dimension | Opus 5.5 (Plotus run, my evidence) | Nemotron 3 Ultra (previous run on record) | Comparable? |
|---|---|---|---|
| Engineering correctness | Schematic: all required blocks, pin map spot-checked, ERC 0 errors/1 unitemised warning. Final board: 5 GND opens (ESD, CC2 Rd, EN cap) | No schematic or PCB artifacts | No (no Nemotron artifact) |
| PCB quality | Neat 74x44 mm, 2 layers, no rounded corners, C5 decap 2.7 mm, USB with test-point stubs | None | No |
| Placement | Done in 11.9 min; DESK gate failed with 1 error; Captain's neatness requirement met visually | None | No |
| Routing | 384 tracks, 28 vias, 42/43 nets, raw DRC 0 clearance/0 short; GND deferred | None | No |
| Power/ground | Power 10 mil; GND via fill polygons, 4 pads + 1 piece unconnected | None | No |
| Manufacturing readiness | Not released; evidence export only, no LCSC in BOM | None | No |
| Total time | 102.83 min of 225 (stage 5 not run) | No engineering clock on record | No |
| CPU/RAM | Mean CPU 64 %, EasyEDA ~41 %, RAM low point 317 MB, GPU idle (remote inference) | 1 sample (CPU 52 %, memory 14.2 GB used of ~15.6 GB, GPU memory 537 MB, 57 C; different sampler) | No (1 point vs 103, different metrics) |
| Model latency | Not measurable locally (remote Claude inference) | Diagnostic report: NIM reasoning model, 3.2 s for a 512-token probe, small-budget failures | No (different measurements) |
| Failure frequency | 20 failures + 3 human events in 103 min (register); 7 in Stage 1 | The diagnostic report lists 5 integration faults before any engineering; no engineering failure log | No |
| Recovery quality | Mostly root-caused with measurements (F-001, F-004, F-009, F-015); two OPEN (F-019, F-020) and one deviation (F-011) | Setup-level repairs documented (backups made, config fixed) | No (different tasks) |
| Human intervention | Pre-clock EasyEDA window reconnect (the designated window id was stale and the Captain had to reconnect it before the clock started), H-001 Apply, H-002 install approval; H-003 declined; 2 requirement additions | The diagnostic work needed a separate model/investigator to repair the Nemotron tool chain (also human-directed) | Partly; interventions are of different kinds |

## What can be said fairly
- Opus 5.5 produced a substantial, traceable, partly complete design with honest self-reporting, but failed a hard electrical gate (GND connectivity) and did not reach manufacturing release.
- The Nemotron folder shows no engineering output to compare; its tool chain required significant repair before it could answer at all. This is not a statement that Nemotron cannot do the task, only that this record contains no attempt.
- No speed claim is made: Opus finished at 102.8 min because a stage failed, not because the task was complete; there is no Nemotron time.
- A fair rerun would give both models the same environment (jar, window id, DESK version), the same telemetry schema and the same stop rules.
