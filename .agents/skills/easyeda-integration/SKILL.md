---
name: easyeda-integration
description: EasyEDA Pro bridge protocol, fast socket discovery, project isolation, and mutation locks.
triggers:
  - "easyeda"
  - "bridge"
  - "socket discovery"
  - "pro api"
  - "drawing js"
inputs:
  project_id: string
  action: string
outputs:
  socket_connected: boolean
  operation_result: dict
authoritative_pipeline: INFRA
replay_safety: MUTATING_LOCK_REQUIRED
---

# EasyEDA Integration Skill

## Purpose
Governs communication with EasyEDA Pro via the high-speed local socket bridge, enforcing project isolation, serialized mutation locks, and API safety.

## When to Use
- Interfacing with an active EasyEDA Pro desktop or web editor instance.
- Discovering bridge socket ports (`49620..49629`).
- Pushing verified block schematics or PCB track updates to the live editor.

## Required Inputs
- EasyEDA Pro project ID or local port specification.
- Verified drawing commands generated via `tools/build.py`.

## Relevant DESK Modules
- `desk/schematic_io.py` + `tools/sch_dump.py`: READ-ONLY schematic read-back (parts, pins, coordinates, nets) — the bridge supports reads; never claim otherwise.
- `tools/wire.py`: wire pins by name (`U1.3`), dry-run by default, `--apply` mutates under the lock and verifies by read-back.
- `desk/orchestrator/agent_loop.py` + `desk/orchestrator/tools_manifest.py`: tool-calling loop for NVIDIA NIM models (`python tools/desk.py agent`).
- `desk/adapters/easyeda_pcb_adapter.py`: Fast bridge socket connector.
- `tools/build.py`: Deterministic EasyEDA command synthesizer.
- `tools/ctx.py api`: Verified API signature inspector.

## Required Engineering Constraints
- Authorization Required: Never run live EasyEDA operations without explicit authorization from the Captain.
- No Custom Drawing Scripts: Never write ad-hoc EasyEDA drawing JavaScript. All drawing commands must originate from `tools/build.py` or `tools/wire.py`.
- No Browser Automation: never drive the EasyEDA UI with a browser tool; every read and write goes through the bridge tools above.
- Verified API Surface: Do not invoke unverified or speculative EasyEDA API methods. Query `python tools/ctx.py api <method>` first.
- Single-Writer Mutation Safety: Enforce single-writer lock; never allow two agents to write to the bridge simultaneously.

## Recommended Workflow
1. Verify API method status: `python tools/ctx.py api <method>`.
2. Discover active bridge socket: Probe candidate ports (`49620..49629`).
3. Acquire serialized project writer lock.
4. Synthesize canvas commands: `python tools/build.py projects/<P> <block_id>`.
5. Transmit verified payload over local socket and await confirmation.
6. Release lock and verify editor document state.

## Validation Steps
- Execute socket bridge unit tests: `python -m unittest tests/test_easyeda_adapter.py`.
- Check live bridge status: `python tools/desk.py bridge status`.

## Failure Conditions & Recovery
- Bridge connection timeout: Verify EasyEDA Pro is running with local API enabled.
- Interrupted dirty write: Execute rollback via `python tools/desk.py recover projects/<P>`.

## Expected Output
- Verified, error-free synchronization of schematic or PCB primitives in EasyEDA Pro canvas.

## Documentation References
- [EasyEDA API Guide](file:///docs/06_EASYEDA_API.md)
- [Live Integration Checklist](file:///docs/LIVE_INTEGRATION_CHECKLIST.md)
