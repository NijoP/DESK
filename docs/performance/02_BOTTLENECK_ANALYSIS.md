# 02 — Comprehensive Bottleneck Analysis

This document provides a systematic analysis of execution latency, memory pressure, I/O boundaries, and computational complexity across DESK workflows.

---

## 1. Ranked Bottlenecks by Measured Impact

| Rank | Bottleneck Subsystem | Nature | Complexity / Latency | Primary Driver |
|---|---|---|---|---|
| **1** | **Freerouting Subprocess Execution** | External Process / CPU | 5,000 – 60,000 ms | Java JVM startup, single-threaded routing search, full-board rip-up/reroute iterations |
| **2** | **EasyEDA Live Bridge Communication** | Network / ECAD Canvas | 200 – 2,500 ms | DOM/canvas mutations in EasyEDA Pro, serialization of large JSON ASTs, IPC socket latency |
| **3** | **Unindexed Pairwise Geometry Checks** | CPU / Geometry | $O(N^2)$ (10 – 250 ms on 500+ pads) | Pairwise pad-to-pad, body-to-body, and track-to-obstacle clearance scans without spatial partitioning |
| **4** | **Unindexed Ratsnest & Crossing Analysis** | CPU / Algorithmic | $O(E^2)$ (5 – 50 ms) | All-to-all line segment intersection tests on unrouted nets without sweep-line bounding boxes |
| **5** | **Repeated Full-Board State Reconstruction** | Memory / CPU | $O(N)$ (2 – 15 ms) | Re-parsing full PCB dump and rebuilding connectivity graphs when only 1 component moved |
| **6** | **Subprocess Ingestion & Output Buffering** | Memory / I/O | $O(S)$ (1 – 10 MB RAM) | Unbounded capture of verbose stdout/stderr during autorouter or DRC runs |
| **7** | **Context Ingestion & LLM Prompt Latency** | AI Latency / Tokens | 800 – 4,000 ms (API bound) | Redundant re-sending of static engineering rules and unchanged block specs |

---

## 2. Detailed Technical Breakdown

### A. EasyEDA Bridge & Mutation Latency
- **Import-Time Discovery**: Early implementations scanned ports 49620..49629 upon module import, introducing 10–50 ms latency even when running purely offline tests.
- **Sequential Mutation Calls**: Mutating 50 components individually across HTTP POST calls required $50 \times 15\text{ ms} = 750\text{ ms}$.
- **Resolution**: `EasyEDAPcbAdapter` provides single-roundtrip batch script generation, collapsing $N$ roundtrips into 1 batched execution.
- **Document Switching Overhead**: Calling `eda.dmt_EditorControl.openDocument()` adds a 600 ms sleep. DESK now skips this when `__D.uuid === doc_uuid`.

### B. Computational Geometry & Spatial Indexing
- **Pad & Body Clearance**: In dense boards (e.g. 500+ pads), an unindexed check performs $\frac{500 \times 499}{2} \approx 125,000$ distance evaluations.
- **Spatial Grid/Quadtree**: Partitioning the board into $2.54\text{ mm}$ bins reduces candidate comparisons by $>90\%$, achieving $O(N)$ expected complexity.
- **Ratsnest Line Crossings**: Naive segment intersection tests all pairs of edges ($E$ edges $\implies O(E^2)$). A sweep-line algorithm with axis-aligned bounding box (AABB) pruning avoids testing non-overlapping bounding segments.

### C. Memory Footprint & Subprocess Management
- **Java JVM Allocation**: Freerouting spawns a separate JVM process consuming 256–1024 MB RAM. Under memory pressure on an 8 GB system, concurrent JVM spawns can trigger OS swapping.
- **Execution Budgeting**: The system must enforce a single external autorouter instance at any time with bounded stdout/stderr buffers (max 2 MB in-memory ring buffer).

### D. Snapshot Invalidation & Incremental Recomputation
- **The Global Invalidation Trap**: When component `C12` is nudged by 0.5 mm, rebuilding the entire board connectivity graph, re-evaluating all ground planes, and re-checking all 400 components wastes computation.
- **Targeted Domain Invalidation**: Only pads belonging to `C12`, nets connected to `C12`, and spatial bins intersecting `C12`'s bounding box require re-evaluation. All other placement, routing, and DRC evidence remains valid.
