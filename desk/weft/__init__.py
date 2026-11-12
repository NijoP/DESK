"""DESK x Weft: Weft orchestrates, DESK engineers.

Weft (https://github.com/WeaveMindAI/weft, O'Saasy licence, pinned in integrations/weft/WEFT_PIN.json) is the
workflow runtime: typed graphs, compilation, durable waits, human approval, run journal.
DESK stays the engineering authority: every DESK node is a thin adapter over a deterministic DESK engine.

    contracts   - typed node contracts (the single source of truth; the .weft node files are generated from them)
    nodes       - node handlers (adapters over DESK engines) and the executor (validation, timeout, retry, idempotency)
    store       - DESK-side records: run traces, idempotent results, approvals, evidence (under <project>/state/weft/)
    service     - loopback HTTP node service that Weft's HttpRequest node calls
    weftgen     - generates integrations/weft/nodes/desk/*.weft from the contracts
    staging     - assembles a runnable Weft project (workflow + DESK nodes + pinned standard library)
    runtime     - detects and drives the `weft` CLI (native or through WSL); never falls back to another orchestrator
    cli         - `python desk.py weft ...`

Zero external Python dependencies. The engineering core does not import this package.
"""

INTEGRATION_VERSION = "0.1.0"
