# Running DESK on an 8 GB laptop

This guide is for a laptop with 8 GB RAM and 2–4 CPU cores, on Windows, Linux or macOS. It describes what DESK
already does on such a machine and the settings an operator can choose.

**Status:** software-tested with fixtures; not validated on a live design. No item below was measured on an 8 GB machine
running EasyEDA. The numbers marked *README* come from the one live run recorded in the README (Windows 11, 15.3 GB RAM).

## Where the memory goes

| Consumer | Memory | Source |
|---|---|---|
| EasyEDA Pro (browser/desktop client) with a board open | ≈ 11–12 GB private memory; free RAM fell to 553 MB | README, live run on 15.3 GB |
| Freerouting (Java) | no heap cap is set by DESK (`desk/routing/orchestrator.py` `build_command`) | code |
| DESK Python engines on the synthetic WATCH-sized board | see `BENCHMARK_REPORT.md` (peak RSS, measured in CI) | CI |
| Mission Control dashboard | one thread per request; one per live SSE stream, capped at 8 | `desk/runtime/server.py` |

The DESK Python engines are not the memory problem on an 8 GB machine. EasyEDA and the Java router are. The guidance
below aims to keep those two from running at full size at the same time.

## What DESK already does

- **Resource tier.** `desk/runtime/resource_profile.py` classifies any host with ≤ 8192 MB RAM, ≤ 2 effective cores,
  < 1500 MB available RAM or memory pressure as `LOW`. Memory pressure means < 600 MB or < 15 % free, or < 500 MB of disk.
  For `LOW`, `desk/runtime/budget.py` gives 1 CPU worker, 2 I/O workers, 1 external process, 100 cache entries,
  a 1 MB stdout buffer and checkpoints every 5 operations. `GET /api/metrics` on the dashboard shows the detected tier.
- **Freerouting threads.** The routing engine runs with `max_threads=1` unless a caller asks for more
  (`desk/routing/orchestrator.py`).
- **Lazy imports.** `desk.routing` and `desk.rework` load submodules on first use. The CI perf job records the cold
  import of the engines measured in `BENCHMARK_REPORT.md`.
- **Dashboard bounds** (this change):
  - every connection gets a 30 s socket timeout;
  - live SSE streams are capped at 8 (`DeskServer(max_sse_clients=...)`), with 503 + `Retry-After` once the cap is reached;
  - request bodies are capped at 1 MiB, and a bad `Content-Length` or `?limit=` is a 400 instead of a pinned or dropped thread.

## Operator settings for 8 GB

These settings are guidance. DESK does not set any of them for you.

1. **Cap the Freerouting heap.** The JVM reads `JAVA_TOOL_OPTIONS`. With 8 GB RAM, set it before routing, for example
   `JAVA_TOOL_OPTIONS=-Xmx1536m`: Windows `set JAVA_TOOL_OPTIONS=-Xmx1536m`, Linux and macOS
   `export JAVA_TOOL_OPTIONS=-Xmx1536m`.
   - **Effect:** a board that needs more heap fails with `OutOfMemoryError` instead of swapping the machine. DESK
     classifies that failure as `ROUTER_RESOURCE_EXHAUSTION` (`desk/reliability/failure_classifier.py`).
   - **Not verified:** the right value for a given board was not measured.
2. **Keep one EasyEDA project and one window open** while routing. The bridge binds to one window, and every extra
   open board costs EasyEDA memory.
3. **Route with one Freerouting thread** (the default). More threads mean more Java heap and more CPU contention with
   EasyEDA.
4. **Use checkpointed, chunked routing** (`state/route/checkpoint/`, `desk/routing/adaptive.py`). This lets a run that
   was stopped for memory continue from the best valid SES, instead of rerouting the whole board.
5. **Leave the dashboard closed, or open in one tab.** Each tab holds one SSE stream (one thread).
6. **Run heavy measurement in CI, not on the laptop.** The `perf` job in `.github/workflows/ci.yml` profiles the
   synthetic board on Linux, Windows and macOS. Locally, `python tools/profile_perf.py --offline --scale 1 --repeat 3`
   is a run of a few seconds on the 41-part board.

## Not done

- DESK does not set a Freerouting heap cap itself, and does not read the `LOW` tier to choose one. That needs a
  measured heap-versus-board-size curve first.
- No end-to-end run of EasyEDA + Freerouting on an 8 GB machine has been recorded. That belongs to the manual
  validation phase (roadmap I-11).
