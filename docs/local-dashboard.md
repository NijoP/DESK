# Local Mission Control & Real-Time Monitoring

DESK includes a built-in, local monitoring dashboard that runs directly on your machine.

When you start an engineering operation—such as schematic synthesis, component selection, placement, routing, copper generation, or manufacturing verification—you can open a local browser tab and watch what DESK is doing in real time.

```text
Default URL: http://127.0.0.1:49620
```

If port `49620` is occupied, DESK automatically binds to the next available port (e.g. `49621`) and prints the active URL to your terminal.

---

## 1. Quick Launch Commands

Start or inspect the dashboard from your terminal:

```bash
# Launch Mission Control and automatically open in default browser
python desk.py dashboard

# Start background HTTP and SSE server on custom port
python desk.py serve --port 49620

# Display formatted terminal status snapshot
python desk.py status

# Output machine-readable JSON status
python desk.py status --json
```

---

## 2. Dashboard Interface

The dashboard is designed as a focused engineering control room:

### A. Executive Header
- **Brand & Version:** System version (`v1.0.0`).
- **Active Project:** Path of the board currently being engineered (`projects/WATCH`).
- **Status Indicator:** Live execution state (`IDLE`, `RUNNING`, `COMPLETED`, `FAILED`, `INTERRUPTED`).
- **Connection Pill:** Real-time Server-Sent Events (SSE) stream indicator with automatic reconnection.
- **Theme Toggle:** Dark (default) and Light engineering color themes.

### B. High-Density Metrics Grid
- **Overall Progress:** Weighted percentage calculated from completed engineering stages.
- **Active Stage:** Currently running stage and elapsed time.
- **Stage Counters:** Tally of `Completed`, `Pending`, and `Failed` stages.
- **Hardware Telemetry:** Real physical measurements of current process RAM, available system RAM, logical CPU cores, and memory pressure.

### C. 12-Stage Engineering Workflow
Visualizes the sequential stages from requirement intake to manufacturing release:
1. **Requirement Ingestion (Gate R):** Dimensions, power tree, GPIO budget.
2. **Schematic Intelligence (M1):** Block decomposition and netlist extraction.
3. **Component Intelligence & BOM (Gate B):** MPN resolution and LCSC sourcing.
4. **Electrical Rules Verification (ERC):** Pin rules and voltage tree checks.
5. **PCB Ingestion:** Board outline geometry and layer stackup.
6. **Mechanical & Placement Analysis (M2):** Anchors, decoupling caps, thermal clusters.
7. **Routing Preparation:** Net priority classification and escape stubs.
8. **Autonomous PCB Routing (M3):** 6-stage priority router and DSN negotiation.
9. **Copper & Ground Generation (M4):** Solid ground planes and power polygons.
10. **DRC & Electrical Verification (M5):** IPC-2221 clearances and annular rings.
11. **Manufacturing Verification (M6):** 8 fail-closed gates and JLCPCB quotes.
12. **Final Engineering Report:** Sign-off summary and artifact packaging.

### D. Live Activity Timeline
A chronological feed of verified events emitted by the engine:
```text
10:31:04  [SYS]  Project loaded: projects/WATCH
10:31:06  [M2]   Board outline geometry verified (100mm x 80mm)
10:31:08  [M1]   BOM resolved: 24 canonical MPNs verified
10:31:12  [M3]   Priority routing: 48/48 nets routed (100%)
10:31:15  [M4]   Ground planes poured with 0.5mm edge setback
10:31:18  [M6]   All 8 hard quality gates VERIFIED
```

### E. Real Engineering Artifacts Table
Displays concrete physical outputs:
- Components processed, nets analyzed, tracks and vias generated.
- DRC violation counts and unconnected net verification.
- Status of all 8 non-negotiable hard acceptance gates.
- Verified manufacturing and PCBA fabrication quotes.

### F. Diagnostic Log Stream
- Searchable and filterable by log level (`INFO`, `WARNING`, `ERROR`, `DEBUG`).
- One-click log copying to clipboard.
- Diagnostic report JSON export for post-mortem debugging.
- Built-in redaction: Tokens, keys, and credentials are automatically stripped before display.

---

## 3. Localhost Security Model

Mission Control is an **offline, local-only** monitoring surface:
1. **127.0.0.1 Binding:** Binds strictly to localhost. Never listens on `0.0.0.0` or public interfaces.
2. **Origin Validation:** Validates `Origin` and `Host` headers to block cross-site request attacks.
3. **Path Traversal Protection:** Rejects paths with `..`, null bytes, or drive delimiters.
4. **Read-Only API:** Only HTTP `GET` requests are processed. Monitoring cannot mutate your PCB files or change engineering decisions.
5. **Non-Blocking Architecture:** If the browser tab is closed or disconnected, background routing, placement, or verification runs to completion without interruption.
