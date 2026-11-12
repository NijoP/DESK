# DESK

**An AI-assisted PCB engineering workbench for EasyEDA Pro.**
Requirements in, verified and manufacturable boards out, with the physics done by code and every board change approved by the engineer.

<p align="center">
  <img src="assets/branding/desk-workflow.png" alt="DESK workflow: requirements, domain intelligence, block schematic, placement, routing, copper and power, DRC and gates, release" width="100%"/>
</p>

[![Python](https://img.shields.io/badge/python-3.9%2B-informational.svg)](https://www.python.org/)
[![Dependencies](https://img.shields.io/badge/dependencies-stdlib%20only-success.svg)](desk/)
[![Tests](https://img.shields.io/badge/tests-713-informational.svg)](tests/)
[![ECAD](https://img.shields.io/badge/ecad-EasyEDA%20Pro-orange.svg)](https://pro.easyeda.com/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Developed by Tusk Innovations Global Pvt Ltd. Pure Python standard library, no pip packages. The one exception is
the optional API-only copper fill, which needs `shapely`.

**Performance metrics:** a timed ESP32-S3 board build in a live EasyEDA Pro project: 66.7 of 225 minutes,
DRC 0, 43/43 nets, full manufacturing package. See [`live-test/`](live-test/README.md).

---

## What DESK does, in engineering terms

You hand DESK a requirements document. It works out what kind of board it is, which electrical rules apply, which component families are needed and what information is still missing. It then drives the schematic, placement, routing, copper and release stages through EasyEDA Pro and Freerouting, while deterministic code calculates trace widths, clearances and creepage, and validators prove the result before anything is released.

Three principles decide how the tool behaves:

1. **Knowledge before geometry.** No part is chosen and no track is drawn until the board's domain, rails, currents and environment are declared.
2. **Physics before appearance.** Widths, clearances and creepage come from IPC-2221, IPC-2221B and IEC 60664-1 formulas and tables in [`desk/ipc.py`](desk/ipc.py), never from a model's guess. An undeclared current or voltage is a hard failure, not a default.
3. **Verification before mutation.** Every live change to a board is planned, checked, applied under a single-writer lock and read back from the ECAD engine. The engineer approves each mutation, and the approval is journalled next to the operation it covers (`DESK_MUTATION_POLICY=require` refuses unapproved ones).

Roles are fixed: **AI reasons, DESK calculates, validators verify, the engineer approves.**

DESK is not a replacement for an ECAD tool or for engineering judgment. It is a co-pilot that refuses to guess.

---

## The workflow

| Stage | What happens | Tool |
|---|---|---|
| 1. Requirements | `REQUIREMENTS.md` with power budget, voltage tree, interfaces, mechanical envelope and GPIO budget (Gate R) | [`docs/00_REQUIREMENTS.md`](docs/00_REQUIREMENTS.md) |
| 2. Domain intelligence | Classify the request into one of 100 PCB archetypes, apply overlays (mains, isolation, RF, motor, battery...), retrieve the rules, list what is missing | `python desk.py domains classify "<text>"` |
| 3. Part selection | Comparison matrix and datasheet-derived passives (Gate B); every MPN resolved against the real EasyEDA library | [`tools/resolve.py`](tools/resolve.py), [`tools/pins.py`](tools/pins.py) |
| 4. Block schematic | Each functional block is a JSON spec; linted offline, drawn on the sheet, then the live netlist is read back and compared with the spec | [`tools/lint.py`](tools/lint.py), [`tools/build.py`](tools/build.py), [`tools/verify.py`](tools/verify.py) |
| 5. Placement | Mechanical constraints first, then decoupling proximity, functional clustering and routability | [`tools/pcb_place.py`](tools/pcb_place.py), [`tools/pcb_check.py`](tools/pcb_check.py) |
| 6. Routing | Nets routed by priority (ground, differential, power, analog, digital, I/O) through Freerouting DSN/SES with pass supervision, stagnation detection and rip-up planning | [`tools/route.py`](tools/route.py) |
| 7. Copper and power | Reference planes, return-path continuity, island detection, IPC-2221 widths per rail, via arrays, voltage-drop estimates | [`desk/copper.py`](desk/copper.py), [`desk/power_distribution.py`](desk/power_distribution.py) |
| 8. DRC and quality gates | Clearance, annular ring, mask dam, fabricator minimums, pad-to-pad copper connectivity, 8 fail-closed acceptance gates | [`tools/drc.py`](tools/drc.py), [`desk/quality.py`](desk/quality.py) |
| 9. Release | Gerber, BOM with LCSC codes, CPL centroids, manifest with hashes; gates run first, exports second, cross-checks third | [`tools/release.py`](tools/release.py) |

The block workflow loop is documented in [`docs/03_BLOCK_WORKFLOW.md`](docs/03_BLOCK_WORKFLOW.md). A failed `verify.py` means the block is cleared and rebuilt from a corrected spec, with a ceiling of two attempts before a human is asked.

---

## Where the numbers come from

| Quantity | Source in code | Method |
|---|---|---|
| Trace width | [`desk/ipc.py`](desk/ipc.py) `calc_trace_width` | IPC-2221 power law `I = k · ΔT^0.44 · A^0.725`, k = 0.048 external / 0.024 internal, from declared current, copper weight and temperature rise. Conservative compared with IPC-2152 chart data. |
| Final width per net | [`desk/profile.py`](desk/profile.py) | `max(net-class width, IPC-2221 width, fabricator minimum)` |
| Clearance | [`desk/ipc.py`](desk/ipc.py), [`desk/profile.py`](desk/profile.py) | IPC-2221B Table 6-1 by working voltage and board location |
| Creepage | [`desk/ipc.py`](desk/ipc.py) | IEC 60664-1 by working voltage, pollution degree and material group; reinforced insulation doubles the distance |
| Fabricator floors | [`desk/manufacturing/jlcpcb/capabilities.py`](desk/manufacturing/jlcpcb/capabilities.py) | Minimum trace, spacing and drill applied as hard lower bounds |

Two things an engineer should know before trusting these:

- The IPC and IEC table values are transcriptions. The flag `verified_against_standard` in `desk/ipc.py` is **False** until a human checks them against the standard text. Every result that depends on them says so.
- The design profile refuses to size copper for a rail whose current is unknown. Routing stops with a `PROFILE:` blocking issue instead of assuming 1 A.

---

## Domain intelligence

New boards are classified before anything is drawn. The library under [`library/pcb_domains/`](library/pcb_domains/) holds:

- **14 domains and 100 archetypes**, from `buck_converter` and `three_phase_bldc_controller` to `isolated_ac_dc`, `lora_transceiver`, `usb_c_interface` and `precision_adc_frontend`. Each archetype lists its typical functional blocks, rails, currents, isolation needs, EMI concerns, thermal considerations, placement and routing priorities, failure modes and the standards that apply.
- **17 overlays** for cross-cutting concerns (mains safety and isolation, galvanic isolation, high current, RF, motor drive, battery management, USB, high-speed digital, precision analog, automotive, harsh environment and more). Overlays stack; a stricter safety rule is never silently discarded when overlays combine.
- **206 component families** with roles, electrical characteristics, required parameters, compatibility and datasheet checks. No part numbers live here: real parts are resolved against the EasyEDA library.
- **66 deterministic rules** with scope, applicability conditions, evaluator, parameters, references, evidence state and enforcement mode. A rule is reported as ENFORCED only when a DESK subsystem actually applies it; otherwise it is ADVISORY or UNSUPPORTED and says so.

```powershell
python desk.py domains classify "LoRaWAN EU868 sensor node, battery powered, 3.3 V, outdoor"
python desk.py domains rules three_phase_bldc_controller --overlays high_current,motor_drive
python desk.py domains validate requirements.json --project projects/MY_BOARD
python desk.py domains check
```

Classification is deterministic (keyword and feature scoring). Ambiguity between mains and low voltage, or around motors and batteries, always returns `REVIEW_REQUIRED` with the questions to ask, never a confident wrong answer. See [`docs/domain_intelligence/NEW_USER_GUIDE.md`](docs/domain_intelligence/NEW_USER_GUIDE.md).

---

## EasyEDA Pro, Freerouting and fabrication

**EasyEDA Pro.** DESK talks to the running desktop or web client through its local JavaScript gateway. It reads back components, pads, tracks, vias, zones, stackup and DRC rules, and writes schematics and PCB changes through two audited paths only: [`tools/build.py`](tools/build.py) for blocks and [`tools/wire.py`](tools/wire.py) for named pins. There is no browser automation and no custom drawing script. Every write goes through a single-writer lock, a baseline hash, a rollback checkpoint and an independent read-back.

**Freerouting.** Boards go out as DSN and come back as SES. DESK runs the engine headless, tracks passes, detects stagnation, plans selective rip-ups and re-verifies connectivity from the returned geometry. A pre-flight gate checks plane nets, outline closure and pads in keep-outs before the engine starts.

**LCSC and JLCPCB.** Parametric search, MPN and C-number resolution, lifecycle (EOL/NRND) and stock, alternatives, PCBA BOM and CPL export, basic/extended part classification and an order guard. Live calls are implemented; automated tests use an offline fixture catalogue.

---

## AI models

DESK routes work through five tiers. L0 is deterministic Python with no model call. L1 to L4 call models of rising capability for reasoning, planning and explanation, with validation on the way back. Providers: NVIDIA NIM over HTTP (default `nvidia/nemotron-3-ultra-550b-a55b`, tool calling verified 2026-11-12), Gemini CLI and the Pi multi-provider CLI.

```powershell
# set NVIDIA_API_KEY in the environment or the DESK credential vault
python desk.py auth configure
python desk.py agent projects/MY_BOARD "read the sheet and list every unconnected pin"
python desk.py agent projects/MY_BOARD "wire U1.VDD to +3V3" --allow-mutation
```

The agent reads the live sheet, plans and explains. It mutates only with `--allow-mutation`, through the same guarded tools an engineer would run by hand. Model output never overrides a calculated width, a verified pin map or a quality gate.

---

## Workflow orchestration (Weft)

Orchestrated workflows are written in [Weft](https://github.com/WeaveMindAI/weft), a typed workflow language with durable runs and human approval steps. Weft orchestrates; DESK engineers: every stage of a workflow is a DESK node that calls one deterministic DESK engine through a local, token-protected service, and only a DESK engine can pass a gate.

```powershell
python desk.py weft status                 # is Weft installed, does it match the pin, is the node service up
python desk.py weft nodes                  # which nodes are backed by an engine, which fail closed and why
python desk.py weft validate               # compile-check the workflows with the Weft compiler
python desk.py weft check-run hardware_design   # would Weft admit the run? (Weft's own admission check, runs nothing)
python desk.py weft run hardware_design --project projects/MY_BOARD --requirements requirements.json
python desk.py weft answer approve.review approve   # a person's decision on a waiting approval
```

Weft is not bundled. It is pinned to an upstream commit (`integrations/weft/WEFT_PIN.json`), runs on Linux or macOS
with Docker (on Windows only inside WSL2), and is built from source at the pin. Without it the engines and every
other tool work as before; `weft run` refuses to start and there is no fallback orchestrator.

**Status: no workflow has been run by a Weft runtime yet.** What is proven on the development machine:

- both workflows compile under upstream's real compiler;
- Weft's own admission check accepts the runs DESK starts;
- the DESK side is tested against the real engines.

Live runs are deferred to a separate Linux machine. The scripted procedure is
[`docs/weft/05_LINUX_VALIDATION.md`](docs/weft/05_LINUX_VALIDATION.md); what is and is not proven is in
[`docs/weft/04_STATUS.md`](docs/weft/04_STATUS.md).

---

## Quick start

Requirements: Python 3.9 or newer (3.11 or 3.12 recommended), Windows 11 is the tested platform. Optional: EasyEDA Pro for live work, Java 17 or newer for Freerouting (Java 25 with Freerouting 2.5.0 is what has been exercised).

```powershell
git clone https://github.com/NijoP/DESK.git
cd DESK

python -m unittest discover -s tests -p "test_*.py"   # no network, no ECAD needed
python -m pip install -e . && desk --version          # optional: the `desk` console command (still zero dependencies)
python desk.py doctor                                 # Python, Java, Freerouting, EasyEDA bridge, config, project binding
python desk.py config show                            # effective configuration: env > ~/.desk/config.json > desk.config.json
python desk.py tools                                  # one line per tool

python tools/new_project.py MY_BOARD                  # projects/MY_BOARD from the template
python desk.py domains classify projects/MY_BOARD/REQUIREMENTS.md
python tools/ctx.py projects/MY_BOARD brief           # where the project is, what comes next
python desk.py dashboard                              # local Mission Control on http://localhost:49630
```

Working on an existing board rather than a new one: `python desk.py rework start|audit|plan|approve|execute|report projects/MY_BOARD` runs an eight-domain audit (requirements, netlist, footprints, placement, routing, power, copper, fabrication), captures a baseline and plans surgical repairs that require an approval token before execution.

---

## Repository map

| Path | Contents |
|---|---|
| [`desk/`](desk/) | Engineering engines: `ipc.py`, `profile.py`, `spec.py`, `copper.py`, `power_distribution.py`, `placement*.py`, `drc_engine.py`, `erc.py`, `quality.py`, `routing/`, `rework/`, `component_intelligence/`, `domain_intelligence/`, `manufacturing/`, `orchestrator/`, `runtime/`, `weft/`; settings in `config.py` |
| [`tools/`](tools/) | Command-line tools for every stage; `python desk.py tools` lists them |
| [`library/`](library/) | Resolved devices, verified pin maps (`library/pins/`), PCB domain knowledge (`library/pcb_domains/`) |
| [`projects/`](projects/) | One directory per board: requirements, block plan, block specs, design profile, ledger |
| [`docs/`](docs/) | Workflow (00 to 09), engineering notes, ecosystem integration, domain intelligence, rework mode, verification |
| [`tests/`](tests/) | Offline unit and fixture tests; live-only checks are skipped unless an ECAD session is present |
| [`integrations/weft/`](integrations/weft/) | Weft workflows, the DESK node library (typed Weft groups) and the pinned upstream commit; Python side in `desk/weft/` |
| [`learning/`](learning/) | Incidents, lessons and playbooks captured from real sessions |
| [`.agents/skills/`](.agents/skills/) | Procedural skills loaded by AI agents; [`AGENTS.md`](AGENTS.md) is the operating manual |

---

## Performance metrics: ESP32-S3 live test (2026-11-12)

A timed end-to-end run of DESK against a live EasyEDA Pro project:
- **Board:** an ESP32-S3-WROOM-1 dev board, 2 layers, 74 × 44 mm, 40 parts, 43 nets.
- **Starting point:** built from an empty schematic and PCB under frozen requirements.
- **Builder:** Claude Opus 5.5 driving DESK (`main` at 2c9de1a).
- **Reviewer:** a separate Claude Sonnet examiner.

Full record: [`live-test/`](live-test/README.md).

### Time (monotonic clock, 225-minute budget, no borrowing between stages)
| Stage | Budget (min) | Used (min) | Share of budget |
|---|---:|---:|---:|
| 1 Schematic | 45 | 11.2 | 25 % |
| 2 Placement | 45 | 12.3 | 27 % |
| 3 Routing | 90 | 33.0 | 37 % |
| 4 Copper | 30 | 3.1 | 10 % |
| 5 Manufacturing | 15 | 6.4 | 42 % |
| **Total** | **225** | **66.7** | **30 %** |

### Design metrics (live readback)
| Metric | Value |
|---|---|
| EasyEDA DRC violations (final) | 0 |
| Nets physically connected (DESK verifier, fills as zones) | 43 / 43 |
| EasyEDA ERC | 0 errors, 2 warnings (text not exposed by the API) |
| Placement routability score | 0.88 |
| Decoupling distance to module power pin | 0.85–0.88 mm |
| USB D+ / D− length (J1 → module) | 63.05 / 63.76 mm (Δ 0.71 mm) |
| USB differential impedance (IPC-2141 estimate) | ≈ 153 Ω (2-layer geometry; ≈ 90 Ω needs 4 layers) |
| Power track width | 0.305 mm (100 of 118 segments), 0.254 mm neck-downs |
| GND pour | top 1668.7 mm², bottom 2095.2 mm²; 41 stitching vias; antenna keep-out copper 0 mm² |
| Silkscreen | 90 texts, min height 0.914 mm, min pad gap 0.358 mm |
| Manufacturing package | Gerber + PTH/NPTH/via drills, BOM with LCSC on 18/18 lines, CPL (40 parts), PDF, `.epro` |
| Failures logged / recovered in-session | 12 / 11 (one crash needed an EasyEDA reopen) |
| Human interventions on the clock | 2 (EasyEDA reopen, Import Changes *Apply*) |

### Examiner score breakdown
| Electrical | Physical | Manufacturing | Evidence and process | Total |
|---:|---:|---:|---:|---:|
| 25 / 30 | 20 / 25 | 21 / 25 | 15 / 20 | 81 / 100 |

### Hardware (Windows 11, 15.3 GB RAM, remote inference)
| Metric | Value |
|---|---|
| CPU mean / peak | 57 % / 75.7 % |
| Free RAM minimum | 553 MB (16 of 67 samples under 1 GB) |
| EasyEDA private memory | ≈ 11–12 GB |
| GPU | idle |

An earlier run under the same requirements is kept in
[`live-test/esp32-s3-plotus/`](live-test/esp32-s3-plotus/) as a baseline: 102.8 minutes, examiner score 50/100.

---

## Verification status

The test suite was last run on 2026-11-12: 717 tests, 0 failures (9 skips). Environment-dependent tests skip when their prerequisite is absent: a Freerouting 2.2+ jar that starts under the local Java (`library/tools` or `FREEROUTING_JAR`; 2.5.0 with Java 25 passes, the unversioned `freerouting.jar` does not), the private project-one fixture, `shapely`, a free EasyEDA bridge port, Node with Backpass, and the git-ignored WATCH routing fixture. `test_orchestrator` 07/10/11 still fail when `DESK_L*_MODEL_PI` or `DESK_FRONTIER_*` are set in the shell. CI runs the suite on Linux, Windows and macOS.

| Area | Status | Evidence |
|---|---|---|
| IPC-2221 width, clearance, creepage calculations | Offline tested; table values not yet checked against standard text | `tests/test_ipc_models.py`, `tests/test_hardware_reference_values.py`, `tests/test_profile_hardening.py` |
| Domain intelligence (taxonomy, classifier, rule engine, profile compiler) | Offline tested; 13 of 100 archetypes exercised by fixtures, 87 are DRAFT entries | `tests/test_domain_taxonomy.py`, `tests/test_rule_engine.py`, `tests/test_cross_domain_cases.py` and six more |
| Routing intelligence, DSN/SES, connectivity, recovery | Offline tested | 11 `tests/test_routing_*.py` files |
| Power distribution, copper planes, return paths | Offline tested | `tests/test_power_distribution.py`, `tests/test_copper_*.py` |
| Placement, DRC, ERC, quality gates | Offline tested | `tests/test_placement.py`, `tests/test_quality_fail_closed.py` |
| Component intelligence, BOM, JLCPCB | Offline tested with fixture catalogue | `tests/test_ci_*.py`, `tests/test_jlcpcb_integration.py` |
| EasyEDA Pro read-back | Live verified (read-only sessions) | [`docs/product_assessment/LIVE_EASYEDA_OBSERVATION_01.md`](docs/product_assessment/LIVE_EASYEDA_OBSERVATION_01.md) |
| NVIDIA NIM tool-calling agent | Live verified against the NIM endpoint, 2026-11-12 | `desk/orchestrator/agent_loop.py` |
| EasyEDA Pro live mutation (placement, copper, routing write-back) | **Exercised live in two timed ESP32-S3 benchmarks**: blocks built, 40 parts placed, rounded outline, SES imported, API-only GND fills and stitching written, silkscreen moved, all read back. Metrics in [`live-test/`](live-test/README.md). Other paths are still not live verified. | [`live-test/`](live-test/README.md), [`docs/product_assessment/LIVE_TEST_STATUS.md`](docs/product_assessment/LIVE_TEST_STATUS.md) |
| API-only copper planes (`pcb_PrimitiveFill`) | Live exercised (Plotus); offline tested. Needs the optional `shapely` package (the tests skip without it) | `tests/test_copper_fill.py`, [`desk/copper_fill.py`](desk/copper_fill.py) |
| Weft orchestration (node contracts, node service, workflows) | Offline tested; workflows compile under upstream's compiler and runs pass upstream's admission check. Linux validation procedure written, **not yet run**. **No run on a Weft runtime yet** | `tests/test_weft_*.py`, [`docs/weft/04_STATUS.md`](docs/weft/04_STATUS.md) |
| Freerouting stopped-job SES with full connectivity | **Not confirmed** | [`docs/engineering/DENSE_BOARD_BENCHMARK_REPORT.md`](docs/engineering/DENSE_BOARD_BENCHMARK_REPORT.md) |

---

## Known limitations

- Live board mutation through the EasyEDA bridge has been exercised in two timed ESP32-S3 benchmarks
  (metrics in [`live-test/`](live-test/README.md)). No controlled live test of each mutation path exists yet; paths not exercised there are marked not live
  verified in source.
- Trace width uses the IPC-2221 power law, not IPC-2152 chart data. Results are conservative for external layers.
- Placement refinement is single pass. It proposes moves; it does not iterate with the router.
- No switching-loop area minimisation and no RF-specific ground-plane synthesis yet. Those rules are ADVISORY in the domain library.
- Junction-temperature and component-rating rules are UNSUPPORTED: DESK lists them, it cannot evaluate them.
- JLCPCB constraints are a static declaration; there is no live DFM or quoting API call.
- Developed and tested on Windows 11. GitHub CI on `main` at `b168be9` (run 43181657514, 2026-11-12) passes on **5 of 8**
  jobs:
  - Passing: Ubuntu with Python 3.11 and 3.12, Windows with 3.11 and 3.12, macOS with 3.12.
  - Python 3.9 on Ubuntu 22.04 and Windows: 4 errors in `test_ci_storage`, because that Python's SQLite has no
    `unixepoch`.
  - macOS with Python 3.11: 1 failure in `test_bridge_port_discovery`.
  - Weft runs are not part of CI (see the Weft section).
- Weft workflows have not been executed by a Weft runtime: durable waits, approval pauses and recovery are unproven, and 22 of the 32 DESK nodes are declared but fail closed until their engine adapter is written.
- Two timed end-to-end benchmarks exist ([`live-test/`](live-test/README.md)):
  - The latest run took 66.7 of 225 minutes; the earlier baseline took 102.8 minutes.

  Treat the other time targets in the docs as targets, not measurements.
- On a 2-layer 1.6 mm board, USB D+/D− cannot reach 90 Ω differential within the module and ESD pad pitch (run 2
  measured about 153 Ω). Use a 4-layer stack-up when impedance control is required.
- `clear_block` leaves frame rectangles, and deleted schematic texts can persist as orphan TEXT records that neither
  the API nor the GUI removes (run 2 R2-F-001/002).
- EasyEDA Pro 3.2's DRC does not reliably connect a via to an API-created fill. `tools/stitch_orphans.py` therefore
  adds explicit tracks.
- `desk/copper_fill.py` is the one module that needs a third-party package (`shapely`). It is imported lazily, so
  the rest of DESK still runs on the standard library only.

---

## Documentation

| Topic | Document |
|---|---|
| Getting started | [`docs/getting-started.md`](docs/getting-started.md) |
| Requirements and part selection gates | [`docs/00_REQUIREMENTS.md`](docs/00_REQUIREMENTS.md), [`docs/00b_COMPONENT_SELECTION.md`](docs/00b_COMPONENT_SELECTION.md) |
| Block workflow, placement, routing | [`docs/03_BLOCK_WORKFLOW.md`](docs/03_BLOCK_WORKFLOW.md), [`docs/04_PLACEMENT.md`](docs/04_PLACEMENT.md), [`docs/05_ROUTING.md`](docs/05_ROUTING.md) |
| Domain intelligence | [`docs/domain_intelligence/NEW_USER_GUIDE.md`](docs/domain_intelligence/NEW_USER_GUIDE.md), [`TAXONOMY_REFERENCE.md`](docs/domain_intelligence/TAXONOMY_REFERENCE.md), [`RULE_CATALOGUE.md`](docs/domain_intelligence/RULE_CATALOGUE.md), [`EVIDENCE_AND_MATURITY_POLICY.md`](docs/domain_intelligence/EVIDENCE_AND_MATURITY_POLICY.md) |
| Routing intelligence | [`docs/ROUTING_INTELLIGENCE_V2.md`](docs/ROUTING_INTELLIGENCE_V2.md), [`docs/engineering/DENSE_PCB_INTELLIGENCE.md`](docs/engineering/DENSE_PCB_INTELLIGENCE.md) |
| Power and copper | [`docs/engineering/POWER_DISTRIBUTION_INTELLIGENCE.md`](docs/engineering/POWER_DISTRIBUTION_INTELLIGENCE.md), [`docs/engineering/COPPER_ZONE_GENERATION.md`](docs/engineering/COPPER_ZONE_GENERATION.md) |
| EasyEDA Pro, LCSC, JLCPCB | [`docs/ecosystem/02_EASYEDA_PRO_INTEGRATION.md`](docs/ecosystem/02_EASYEDA_PRO_INTEGRATION.md), [`docs/ecosystem/LCSC_INTEGRATION_ARCHITECTURE.md`](docs/ecosystem/LCSC_INTEGRATION_ARCHITECTURE.md), [`docs/ecosystem/JLCPCB_MANUFACTURING_ARCHITECTURE.md`](docs/ecosystem/JLCPCB_MANUFACTURING_ARCHITECTURE.md) |
| Rework mode for existing boards | [`docs/rework/01_REWORK_MODE_OVERVIEW.md`](docs/rework/01_REWORK_MODE_OVERVIEW.md) |
| Context engine and learning | [`docs/07_CONTEXT_ENGINE.md`](docs/07_CONTEXT_ENGINE.md), [`docs/08_LEARNING_ENGINE.md`](docs/08_LEARNING_ENGINE.md) |
| Weft orchestration | [`docs/weft/01_ARCHITECTURE.md`](docs/weft/01_ARCHITECTURE.md), [`02_INSTALL.md`](docs/weft/02_INSTALL.md), [`03_LICENCE.md`](docs/weft/03_LICENCE.md), [`04_STATUS.md`](docs/weft/04_STATUS.md), [`05_LINUX_VALIDATION.md`](docs/weft/05_LINUX_VALIDATION.md) |
| Mission Control dashboard | [`docs/local-dashboard.md`](docs/local-dashboard.md) |
| Live test status and checklist | [`docs/product_assessment/LIVE_TEST_STATUS.md`](docs/product_assessment/LIVE_TEST_STATUS.md), [`docs/LIVE_INTEGRATION_CHECKLIST.md`](docs/LIVE_INTEGRATION_CHECKLIST.md) |
| Agent operating manual | [`AGENTS.md`](AGENTS.md) |

---

## Contributing

1. Python standard library only. No new pip dependencies; the single optional one (`shapely`, API-only copper fill) is imported lazily.
2. Read settings through `desk.config`, never `os.environ` directly (`tests/test_config.py` enforces it).
3. Every width, clearance or creepage rule must cite a formula, a standard table or a fabricator document. No magic numbers.
4. Never weaken a quality gate, bypass DRC or connectivity checks, or replace missing evidence with confidence.
5. Run the full suite before and after a change: `python -m unittest discover -s tests -p "test_*.py"`. Zero failures, zero errors.
6. Read [`AGENTS.md`](AGENTS.md) for conventions, the block workflow and the safety rules.

## License

[MIT](LICENSE). See [NOTICE](NOTICE) for attribution.
