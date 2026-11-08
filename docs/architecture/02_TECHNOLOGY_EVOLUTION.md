# Technology Evolution Strategy: Python, Rust & TypeScript

**Author:** Principal Software Architect & Systems Performance Lead  
**Scope:** Architecture Roadmap, Inter-Process Boundaries, and FFI Data Contracts  
**Repository:** https://github.com/NijoP/DESK  
**Status:** Canonical Roadmap

---

## 1. Architectural Philosophy

DESK rejects dogmatic technology rewrites. A software system is not improved by simply rewriting functional algorithms into another programming language without evidence.

We follow a strict migration policy:
1. **Audit First**: Verify correctness of algorithms in Python.
2. **Measure Second**: Profile end-to-end execution across T1–T13.
3. **Correct Third**: Eliminate algorithmic defects and data structure bottlenecks.
4. **Optimize Fourth**: Implement native caching and incremental recalculation.
5. **Migrate Only When Justified**: Migrate a component to Rust or TypeScript only when empirical benchmarks prove a critical latency, memory, or concurrency bottleneck that cannot be resolved in Python.

---

## 2. Technology Division of Responsibility

```
┌─────────────────────────────────────────────────────────────┐
│                 TypeScript / Node.js Engine                 │
│  - EasyEDA Pro API Gateway Communication (IPC socket)        │
│  - Native Electron / Webview CAD document integration       │
│  - Real-time CAD DOM mutation scripts                       │
└──────────────────────────────┬──────────────────────────────┘
                               │ JSON / IPC / Socket
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                       Python Engine                         │
│  - Master engineering orchestration & lifecycle state       │
│  - IPC-2152 & IPC-2221 electrical standards calculations    │
│  - DesignProfile & Manufacturing rule definitions           │
│  - Fail-closed Quality Acceptance Gates (5-state lifecycle)  │
│  - Component Intelligence, LCSC & JLCPCB API client logic   │
└──────────────────────────────┬──────────────────────────────┘
                               │ PyO3 / C-ABI FFI Contracts
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                    Rust Accelerated Engine                  │
│                   (Targeted Selective Modules)              │
│  - Computational Geometry & Clipper polygon clipping         │
│  - R-Tree spatial indexing over 10,000+ pads/tracks         │
│  - Native Multi-Terminal MST & A* maze routing grid         │
│  - Incremental PCB snapshot hash digests                    │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Language-Independent Data Contracts

Versioned contracts reside in `desk/contracts/`:
- **`geometry.py`**: Points, Rectangles, Polygons, Keepouts, and Collision Results. Matches C-ABI memory layouts for zero-copy sharing with Rust.
- **`routing.py`**: Net endpoints, track segments, vias, and routed net connectivity graphs.
- **`bridge.py`**: Structured requests, responses, and document metadata for TypeScript API Gateway interchange.

---

## 4. Empirical Migration Justification Thresholds

A module is approved for Rust acceleration only if:
1. **CPU Bound**: Python execution exceeds 50 ms in typical boards ($> 500$ pads).
2. **Memory Bound**: Python object overhead exceeds 50 MB for geometry caches.
3. **Concurrency Bound**: Global Interpreter Lock (GIL) prevents parallel raycasting across multiple cores.

Currently, pure algorithmic pipelines in DESK execute in **$< 6.0\text{ ms}$** in pure Python standard library, confirming that Python remains highly performant for typical boards when algorithms and data structures are correctly implemented.
