# Simulation plugin (optional): `desk/simulation/`

> **Simulation alone does not prove a PCB is electrically or thermally safe.** A simulation is one
> piece of evidence. Combine it with hand calculations (`desk/calc.py` qa entries), datasheet
> verification and independent engineering checks. Status: software-tested with fixtures; not
> validated on a live design.

DESK core does not depend on any simulator. `desk.simulation` imports no engine, so with ngspice
absent every DESK module imports and every test passes. The ngspice adapter is imported only when
the `ngspice` engine is requested. `desk.py doctor` reports it as an optional check: `WARN` when
missing, never `FAIL`.

## Pieces

| Module | Role |
|---|---|
| `base.py` | `Simulator` interface, result data model (`SimulationResult`, `AnalysisResult`, `Measurement`, `Diagnostic`), error categories, engine registry (`register`, `get`, `engines`) |
| `netlist.py` | SPICE netlist from a block spec plus a sim spec. Supports R, L, C, D, Q (BJT), M (MOSFET), X (subcircuit) and V/I sources. Unsupported parts are reported, never dropped |
| `models.py` | Model store (`library/sim_models.json` by default). Records each card's source and status `TRACEABLE`/`UNVERIFIED`. Refuses unsafe cards |
| `ngspice.py` | Batch adapter: deck rendering, isolated subprocess run, ASCII raw and log parsing, error classification |
| `verify.py` | Checks results against expected ranges from the calculation layer and gives a fail-closed verdict |
| `export.py` | CSV per analysis and `result.json` for plotting. No plotting dependency |
| `cli.py` | `desk.py sim engines|netlist|run|models` |

Supported analyses: DC operating point (`op`), transient (`tran`) and small-signal AC (`ac`).
Priorities: analog stages, switching-converter power stages, power electronics and mixed-signal
building blocks.

## Simulation spec

A block spec (`projects/<P>/blocks/NN_ID.json`) gives parts, values and pin->net maps. The sim spec
adds what a schematic does not carry: stimulus, analyses, measurements, models, and explicit
terminal maps. Pin numbers are never guessed, so every diode, transistor and subcircuit needs one.
The full format is in the `desk/simulation/netlist.py` docstring. Worked synthetic examples are in
`tests/fixtures/simulation/*/case.json` (divider, RC step, buck stage).

```json
{"ground": ["GND"],
 "parts": {"Q1": {"element": "M", "model": "NSW", "terminals": {"D": "3", "G": "1", "S": "2"}},
           "D1": {"element": "D", "model": "DSCH", "terminals": {"A": "2", "K": "1"}},
           "J1": {"exclude": "input pad, no electrical model"}},
 "sources": [{"name": "VIN", "kind": "V", "pos": "VIN", "neg": "GND", "dc": 12}],
 "analyses": [{"type": "tran", "step": 5e-7, "stop": 4e-4, "uic": true, "linearize": true}],
 "measures": [{"name": "vout_avg", "analysis": "tran", "expr": "AVG v({VOUT}) FROM=350u TO=400u"}],
 "save": ["v({VOUT})"]}
```

`{NET}` expands to the SPICE node of that net. Ground nets map to node 0. Two nets that only differ
in case are refused, because SPICE would merge them.

## Models and provenance

`TRACEABLE` means the card's source is a datasheet or a vendor model library, and the reference names
the document. DESK has not checked such a card against the datasheet curves. Everything else is
`UNVERIFIED`: generic cards, hand-tuned cards, and cards written inline in a sim spec. A result that
uses an `UNVERIFIED` model can at best reach `PASS_WITH_CAVEATS`. `desk.py sim models check` exits
1 while any model is `UNVERIFIED`.

## Running ngspice

- one temporary working directory per run (`--out <dir>` keeps it under `<dir>/engine`)
- `ngspice -b -n -o desk.log desk.cir`: batch mode, no `.spiceinit`, stdin closed
- DESK writes the control block. Measures and analysis markers live there, and user model cards
  cannot contain control, include or shell statements
- `DESK_SIM_TIMEOUT_S` (default 60) kills a run that takes too long. A result file larger than
  `DESK_SIM_MAX_OUTPUT_MB` (default 64) is refused, and log reads are capped at 2 MB
- ngspice exits 0 after an aborted transient and after ignoring a malformed element line. DESK
  therefore classifies the log, not the exit code

Error categories: `ENGINE_NOT_FOUND`, `TIMEOUT`, `NETLIST_ERROR`, `MODEL_ERROR`, `CONVERGENCE`,
`CONVERGENCE_ASSISTED` (warning: it converged only through gmin/source stepping), `MEASURE_FAILED`,
`OUTPUT_TOO_LARGE`, `NO_OUTPUT` (including a stale plot from an earlier analysis) and
`ENGINE_CRASH`.

## Verification

```json
[{"quantity": "vout_avg", "min": 4.3, "max": 5.1, "unit": "V", "source": "D*Vin - drops"},
 {"quantity": "op1:v({VOUT})", "min": 4.9, "max": 5.1, "unit": "V", "source": "divider formula"}]
```

`--expect-qa` derives expectations from a block's qa entries that carry `"sim": "<quantity>"`. The
value desk.calc computed from the entry's `expr` is attached. With `"sim_tolerance": 0.01` the
simulated value must also be within 1 % of that calculation.

| Verdict | Meaning |
|---|---|
| `PASS` | every check passed, every model is TRACEABLE, no warnings, no excluded parts |
| `PASS_WITH_CAVEATS` | checks passed, but with UNVERIFIED models, warnings or excluded parts (listed) |
| `FAIL` | a value is out of range, a measurement failed or is missing, or sim and calculation disagree |
| `NOT_RUN` | the simulation did not complete (engine missing, netlist/model error, convergence, timeout) |
| `NO_EXPECTATIONS` | completed, but nothing was checked |

`desk.py sim run` exits 0 only for `PASS`, or for a completed run with no expectations.

## CLI

```bash
python tools/desk.py sim engines
python tools/desk.py sim netlist sim.json --block projects/<P>/blocks/NN_ID.json
python tools/desk.py sim run sim.json --block <block.json> --expect expect.json --out <dir>
python tools/desk.py sim models check [--models <store.json>]
```

## Not implemented yet

- ngspice shared-library integration. Batch mode only. Evaluate it later where it gives a measured benefit
- thermal simulation
- DC sweep, noise, Monte Carlo/corner and parameter-sweep analyses
- binary raw files (DESK always requests ASCII)
- engines other than ngspice (the registry is ready for them)
- automatic import of vendor model libraries, and checking cards against datasheet curves
- schematic or PCB integration. Sim specs are written by hand next to the block spec
