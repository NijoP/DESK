# Hardware Performance Report (independent)
Source: evaluation\HARDWARE_RESOURCE_METRICS.csv, 103 rows, 04:51:36 to 06:33:58 +05:30, one row per ~60 s, collector PID 33512 (read-only; stopped at the end of this evaluation). Machine: Windows 11, 15.3 GB RAM (15655 MB), 174 GB free on C: at start, Nvidia GPU present. Engineering clock 04:50:28 to 06:33:18 (102.83 min).

## Collection caveats (honest)
- First collector launch (PID 30644) failed (unquoted path); data starts 04:51:36, so the first 1 min is missing. First row's per-process CPU is 0 (no prior sample).
- 60 s sampling misses short bursts (python processes read 0 % at every sample although DESK scripts ran; they were sub-minute).
- No NA cells (every reading succeeded), including nvidia-smi. Per-process CPU% is total-CPU-normalised (TotalProcessorTime delta / wall / logical CPUs).
- Inference is remote: local GPU idle is expected, and model latency cannot be derived from local telemetry.

## Summary table (04:52-06:34)
| Metric | min | mean | p95 | max |
|---|---:|---:|---:|---:|
| Overall CPU % | 49.8 | 64.4 | 79.2 | 96.1 (05:46:47) |
| EasyEDA CPU % (of total) | 37.0 | 40.9 | 42.8 | 44.6 |
| Claude Code CPU % | 0.6 | 1.2 | 1.8 | 2.7 |
| Claude Code working set MB | 1271 | 1681 | 2013 | 2065 |
| Claude Code private MB | 3765 | 4112 | 4622 | 4693 |
| node working set MB | 25 | 34 | 39 | 126 |
| EasyEDA working set MB | 1549 | 2202 | 2640 | 2994 |
| EasyEDA private MB | 5171 | 6655 | 7441 | 7679 |
| Java (Freerouting) CPU % | 0 | 2.5 | 13.4 | 18.4 (only while routing) |
| Java working set MB | 0 | 314 | 1202 | 1333 |
| Available RAM MB | 317 (06:02:52) | 1507 | 2277 | 2423 |
| C: free GB | 157.33 | 162.2 | 162.9 | 174.43 |
| Disk read MB/s | 0 | 4.3 | 6.6 | 154.8 (05:47:47) |
| Disk write MB/s | 0 | 1.4 | 2.3 | 68.2 |
| Network MB/s (all interfaces) | ~0 | 0.34 | 1.2 | 5.46 |
| GPU util % / mem MB | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| GPU temp C | 46 | 48.2 | 51 | 52 |
| Processes / threads | 390 / 6461 | 405 / 6680 | 415 / 6871 | 418 / 7236 |

## Findings
1. Dominant local consumer: EasyEDA, a steady ~41 % of total CPU for the whole run (even when the builder was idle or thinking) and 2-3 GB working set with 5-7.7 GB private memory. It is the likely cause of the 120 s bridge timeouts at 04:58-05:02 (correlated with RAM low point 579 MB; causation not established; the builder's stale-library-uuid root cause for F-001 has the stronger evidence).
2. Memory pressure episodes: available RAM fell below 900 MB at 04:58-05:02, 05:32-05:42 (670-900 MB), 05:57 (872 MB), 06:02:52 (317 MB, lowest), 06:06:53 (859 MB) and 06:21-06:25 (795-900 MB). Each coincided with EasyEDA plus a Freerouting JVM (1.1-1.3 GB). No crash or out-of-memory event was observed, but the machine had only ~1.5 GB mean headroom out of 15.3 GB.
3. EasyEDA private memory rose from 5.2 GB (start) to 7.35 GB (end); Claude Code working set grew from ~1.55 to 2.06 GB (+0.5 GB over 102 min, steady). Neither looks like a runaway leak, but both only grew.
4. Freerouting: 13-18 % total CPU (about 1-1.5 cores of the machine's logical CPUs), ~1.2 GB WS, intermittent: 05:41-05:58 (runs 1-2), 06:00-06:02, 06:06, 06:19-06:28 (run7, killed after 600 s with no output).
5. C: free fell 174.4 -> 162.9 GB at 04:58 (unexplained 11.5 GB step, not identified) and 162.4 -> 157.8 GB during copper/export (06:30-06:33; Gerber/DRC dumps and temporary files, plausible). Net -16.6 GB over the run.
6. Network: mean 0.34 MB/s, ~2.1 GB integrated over the run (approximate; 60 s samples). Known source: ~67 MB Freerouting jar at 05:39:45. Repeated 5.4 MB/s bursts at 05:51, 06:10, 06:18-06:21 are NOT attributed (could be Claude Code context traffic or unrelated background apps); I do not claim a cause.
7. Disk: bursts up to 155 MB/s (05:47:47, around first router run) and 68 MB/s write, otherwise light. Not a bottleneck.
8. GPU: 0 % util, 0 MB used at all 103 samples; temperature 46-52 C. Expected: remote inference, EasyEDA not GPU-bound.
9. Process/thread counts stable (390-418 / 6.5-7.2k): no process leak.

## Bottleneck conclusion
CPU is moderate (mean 64 %, p95 79 %). The real constraint is RAM headroom when EasyEDA and a Freerouting JVM run together, plus EasyEDA's constant CPU use. No local GPU, disk or network bottleneck. Remote model latency is unobserved here.
