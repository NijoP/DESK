# Hardware performance report - run 2b (13:54:08-15:00:50), from HARDWARE_RESOURCE_METRICS.csv
Collector: read-only, 60 s sampling (some 30 s earlier). 171 rows total (12:12:50-15:03:38); 67 inside the run 2b clock; 101 in attempt 1. Machine: 15,655 MB RAM, GPU none/0%.
| Metric (run 2b) | min | mean | p95 | max |
|---|---:|---:|---:|---:|
| CPU total % | 49.6 | 57.1 | 69 | 75.7 |
| EasyEDA CPU % (of machine) | 38.5 | 42.0 | 43.4 | 46.3 |
| EasyEDA working set MB | 2455 | 2969 | 3422 | 3743 |
| EasyEDA private MB (13 procs) | 11028 | 11424 | 11918 | 12169 |
| Claude CPU % | 0.6 | 1.1 | 1.7 | 2.3 |
| Claude working set MB | 1744 | 1870 | 1960 | 1985 |
| Java (Freerouting) CPU % | 0 | 1.0 | 12.7 | 14.3 |
| Java working set MB | 0 | 124.5 | 1240.5 | 1314.8 |
| Python working set MB | 0 | 11.0 | 38.4 | 98.7 |
| Node working set MB | 17.9 | 30.7 | 35.1 | 78 |
| RAM available MB | 553 | 1470 | 2123 | 2305 |
| C: free GB | 152.98 | 154.2 | 156.3 | 156.3 |
| Disk read B/s | 0 | 1.86 M | 12.8 M | 19.2 M |
| Disk write B/s | 0 | 1.35 M | 8.9 M | 20.5 M |
| Net B/s | 1348 | 134 K | 724 K | 2.36 M |
| GPU util % | 0 | 0 | 0 | 0 |
| Processes / threads | 378 / 6254 | 387 / 6451 | 406 / 6820 | 412 / 6909 |
Attempt 1 (12:12-13:53, n=101): CPU mean 53.9 (max 69.6); free RAM min 440, mean 1977; EasyEDA private mean 10.3 GB.

## Findings
- Bottleneck: memory, not CPU. EasyEDA holds ~11-12 GB private across 13 processes on a 15.6 GB machine; free RAM was under 1000 MB in 16 of 67 samples (lowest 553 MB at 14:14-14:24, attempt 1 low 440 MB). This matches the builder's suspected OOM crash (R2-F-004) but the 60 s sampling never showed the EasyEDA process count dropping, so the crash is not telemetry-confirmed.
- EasyEDA sits near 40% of total CPU continuously (idle too); the machine baseline is ~50% before any load. The rest of the toolchain (Claude, Python, Node) is negligible. Freerouting (Java) peaked ~1.3 GB and 14% CPU only in the two router runs (~14:19-14:23 and 14:32-14:37).
- Disk, network and GPU are not constraints (GPU unused). Low C: free is not an issue (153 GB).
- Limitation: 60 s resolution and per-process-name groups; a short crash/restart inside one interval is invisible.
- Recommendation: more RAM or fewer EasyEDA windows/projects; recover with fresh EasyEDA between runs.
