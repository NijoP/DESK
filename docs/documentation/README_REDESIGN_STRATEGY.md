# DESK README Redesign Strategy: Electronics-Engineer-First

**Document Status:** Approved Architecture & Communication Specification  
**Primary Audience:** Electronics and Hardware Design Engineers  
**Target ECAD Tool:** EasyEDA Pro (Desktop / Client API)  
**Author:** Principal Developer Productivity Architect & Hardware Workflow Specialist  

---

## A. Primary Audience

The primary reader is an **electronics, PCB, or hardware development engineer**.

### Characteristics & Knowledge Base:
- **Core Competencies:** Understands schematics, symbols, electronic components, datasheets, netlists, footprints, track geometry, vias, copper planes, Design Rule Checks (DRC), Bill of Materials (BOM), and manufacturing packages (Gerbers, drill files, pick-and-place files).
- **Tooling Context:** Experienced with ECAD suites (specifically EasyEDA Pro, Altium, KiCad, or Eagle) and lab test bench workflows (multimeters, oscilloscopes, power supplies).
- **Software Exposure:** May have minimal or zero background in software development. Typically does not use Python, does not build web APIs, does not write JSON schemas, does not manage asynchronous event buses, and does not want to navigate software architecture diagrams to understand if a tool helps their circuit design.
- **Key Requirement:** Needs to know what physical engineering operations DESK performs on their circuit, how it coordinates with EasyEDA Pro, how it safeguards their existing artwork, and how to operate it without becoming a software developer.

---

## B. Reader Problems & Practical Inquiries

When a hardware engineer discovers the DESK GitHub repository, they bring practical engineering questions:

1. **Relevance:** *"Is DESK an ECAD editor, an autorouter, an AI chatbot, or something else? Does it replace EasyEDA Pro or work with it?"*
2. **Design Assistance:** *"Can DESK help me take my schematic into a completed PCB layout, route tricky traces, or size power tracks according to real current limits?"*
3. **Existing Work Preservation:** *"I have an inherited or unfinished PCB. If I connect DESK, will it scramble my placed components, delete my existing hand-routed tracks, or can it respect what I have already done?"*
4. **Verification & Quality:** *"How does DESK know if my board is actually ready for manufacturing? Does it just count DRC errors, or does it check electrical return paths and copper continuity?"*
5. **Practical Operation:** *"What software do I need to install on my Windows workstation, how do I start it, and what does the screen look like when it runs?"*
6. **Safety & Control:** *"Do I have human sign-off on changes before they happen to my board, or does an algorithm silently edit my files?"*

---

## C. Recommended README Story & Reader Mental Journey

The README must strictly follow an **electronics-engineer-first progression**:

```
1. Product Identity
   "DESK — Your electronics engineering workbench."
   (What it is, who it is for, what it connects to)
        │
        ▼
2. The Engineering Problem ("Why DESK?")
   (Schematic done but PCB isn't, power tracks undersized,
    split planes, DRC clearance errors, inherited boards)
        │
        ▼
3. What is DESK?
   (A workbench alongside EasyEDA Pro that provides
    engineering intelligence, deterministic calculation, and verification)
        │
        ▼
4. What Can You Do With DESK?
   (Schematic inspection, components, placement, routing,
    copper/ground, checking, mission control, manufacturing outputs)
        │
        ▼
5. How DESK Fits into Your Engineering Workflow
   (Clear engineer-to-board flow diagram)
        │
        ▼
6. Choose What You Want to Do
   (New design vs. continuing an unfinished PCB vs. read-only audit)
        │
        ▼
7. What Do You Need Before Starting?
   (Hardware checklist: computer, Python, EasyEDA Pro)
        │
        ▼
8. Installation & Setup
   (Tested, copy-paste Windows PowerShell / Linux commands)
        │
        ▼
9. Your First DESK Session
   (Step-by-step walkthrough of starting and checking a board)
        │
        ▼
10. Protecting Your Engineering Work
    (Baseline snapshots, single-writer safety, change approvals)
        │
        ▼
11. What Happens When Work is Finished?
    (Manufacturing readiness: 8 hard gates, release package)
        │
        ▼
12. Current Capabilities & Status Table
    (Honest evidence-based status: implemented, offline tested, live verified)
        │
        ▼
13. Engineering Accuracy & Performance
    (IPC-2152 trace sizing, thermal rise, real execution benchmarks)
        │
        ▼
14. Documentation Index & Guides
    (Task-oriented index linking to deep technical guides)
        │
        ▼
15. Repository Structure
    (Simple 6-row engineering purpose table)
        │
        ▼
16. Limitations, Responsibilities & License
    (Clear boundaries, professional review obligation, MIT license)
```

---

## D. Language Strategy

### 1. The Laboratory Analogy Rule
Write as though explaining DESK to a fellow hardware engineer at a lab bench. Lead with the **physical, electrical, and mechanical result**, not the software implementation.

### 2. Plain-Language Translations

| Software-Centric Term (Avoid Leading With) | Electronics Engineering Translation (Use in Primary Text) |
|---|---|
| "Event-driven execution projection" | "Real-time task tracking so you can see which PCB operation is active" |
| "Domain-specific revision fingerprint" | "Board revision tracking to detect if the PCB was modified since last check" |
| "Bounded multi-stage priority scheduler" | "Priority routing order: ground and power rails before general digital signals" |
| "Fail-closed hard acceptance gates" | "Non-negotiable manufacturing checks: zero shorts, zero opens, 100% net connection" |
| "Single-writer mutex on canvas primitives" | "Single-writer safety lock that prevents simultaneous, conflicting board edits" |
| "Specctra DSN grammar generator" | "Automated export and tuning of industry-standard routing files" |
| "Parametric supplier scraper" | "Component search across LCSC and distributors for stock and part numbers" |
| "Ray-casting point-in-polygon engine" | "Copper plane continuity and floating copper island detection" |

### 3. Preserved Hardware Terms (With Clear Explanations)
Keep standard hardware terms intact, but provide a 1-sentence definition on first use:
- **Track width & ampacity (IPC-2152):** Sizing copper traces so they do not overheat under operating current.
- **Return path:** The path electrical current takes through ground planes back to its source; discontinuities cause noise and EMI.
- **Design Rule Check (DRC):** Automated verification that clearances, track widths, and drill sizes satisfy manufacturer limits.
- **Thermal relief:** Spokes connecting component pins to copper planes that allow soldering without excessive heat sinking.
- **Stitching vias:** Arrays of ground vias connecting top and bottom copper planes to reduce noise and lower ground impedance.

---

## E. Existing README Problems & Solutions

| Existing README Issue | Root Cause | Engineer-First Solution |
|---|---|---|
| Leads with badges, Python version, and software dependencies. | Software repository template bias. | Move product identity and hardware engineering problems to the top; badges are compact and secondary. |
| Explains internal classes (`DesignProfile`, `RoutingPriorityScheduler`, `SessionRegistry`). | Written from developer codebase perspective. | Explain capabilities in terms of engineering activities: "Sizing power tracks", "Planning routes", "Pouring copper". |
| Heavy focus on REST API endpoints and SSE streaming protocol. | Software architecture perspective. | Describe "Local Mission Control" as an in-browser engineering dashboard showing live project status, stage progress, and errors. |
| Confusing distinction between offline mathematical calculations and full CAD routing. | Raw microbenchmarks (`0.02ms`) make it seem like an entire board is routed in microseconds. | Clearly distinguish sub-millisecond mathematical algorithms (MST, IPC-2152) from multi-second complete board autorouting and live ECAD synchronization. |
| Missing practical first-time user walkthrough. | Assumes user knows how to invoke internal tools. | Provide an explicit 10-step "Your First DESK Session" with exact commands and expected terminal outputs. |

---

## F. Proposed README Table of Contents (18 Sections)

1. **Product Identity** (`# DESK — Your electronics engineering workbench.`)
2. **The Engineering Problem** (`Why DESK?`)
3. **What is DESK?** (Workbench alongside EasyEDA Pro)
4. **What Can You Do with DESK?** (8 engineering capability subsections)
5. **How DESK Fits into Your Engineering Workflow** (Simple workflow diagram)
6. **Choose What You Want to Do** (New Design, Unfinished Board Rework, Read-Only Audit)
7. **What Do You Need Before Starting?** (Hardware engineer's checklist)
8. **Install DESK** (Tested PowerShell, Linux, macOS commands)
9. **Your First DESK Session** (Step-by-step walkthrough)
10. **How DESK Protects Your Engineering Work** (Snapshots, approvals, lockouts)
11. **What Happens When the Work is Finished?** (4 clear readiness states)
12. **Current Capabilities and Development Status** (Authoritative evidence table)
13. **Performance and Engineering Accuracy** (Physics-based derivation & benchmarks)
14. **Documentation: Find What You Need** (Task-oriented documentation index)
15. **Repository Structure** (Concise 6-row directory table)
16. **Who is DESK For?** (Target hardware personas)
17. **Limitations and Responsibilities** (Transparent boundaries & engineer sign-off)
18. **Contributing and License** (MIT License & engineering standards)

---

## G. Feature Evidence Mapping

Every claim in the rewritten README must tie directly to verified source code and test results:

| Capability Claimed | Source Module | Automated Tests | Testing Scope |
|---|---|---|---|
| **IPC-2152 Trace Width Calculation** | `desk/profile.py` | `tests/test_profile_hardening.py` | Verified offline with physical formulas (1oz/2oz copper, internal/external). |
| **6-Stage Net Priority Scheduling** | `desk/router.py` | `tests/test_router_hardening.py` | Verified offline on multi-terminal netlists. |
| **Copper Planes & Split Return Paths** | `desk/copper.py` | `tests/test_copper_geometry.py` | Verified offline via 2D ray-casting polygon engine. |
| **8 Fail-Closed Hard Acceptance Gates**| `desk/quality.py` | `tests/test_quality_fail_closed.py` | Verified offline; strictly blocks unrouted or shorted boards. |
| **Local Mission Control Dashboard** | `desk/runtime/server.py`<br>`desk/ui/assets/index.html` | `tests/test_server.py`<br>`tests/bench_server_overhead.py` | Verified offline on `127.0.0.1:49630`; read-only enforcement tested. |
| **Live EasyEDA Pro TCP Bridge** | `desk/bridge.py`<br>`desk/adapters/` | `tests/test_bridge_port_discovery.py` | Quarantined to disposable workspaces; fast port discovery tested. |
| **Rework & Inspection Architecture** | `desk/rework/` | In development | Mode detection, baseline capture, and readiness modules implemented. |

---

## H. Acceptance Criteria (Hardware Engineer Perspective)

The completed `README.md` will be evaluated against these non-negotiable criteria:
1. **Zero Software Gatekeeping:** An engineer can read Sections 1–6 without encountering a single Python class, decorator, or software design pattern.
2. **Immediate Problem Recognition:** An engineer immediately recognizes their own workflow bottlenecks (routing congestion, thermal sizing, return path splits, DRC debugging).
3. **Copy-and-Paste Usability:** The installation and first-session commands can be pasted directly into Windows PowerShell and run without errors.
4. **Honest Capability Boundaries:** Experimental or in-development features are clearly labeled as such; no unverified claims.
5. **Flawless GitHub Rendering:** Markdown and Mermaid syntax must render cleanly on GitHub desktop and mobile without any parse errors.
