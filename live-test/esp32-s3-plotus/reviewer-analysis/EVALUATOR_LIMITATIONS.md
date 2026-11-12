# Evaluator limitations
- The examiner run was ended by a harness handback at ~05:01; T+20 (due 05:10:28) was written ~05:21 retroactively from file mtimes and logs, not live. Continuous supervision was NOT achieved.
- Background timers/monitors only wake the examiner while its run is active; between turns it relies on coordinator "checkpoint" messages.
- Telemetry is sampled every 60 s: short CPU/disk bursts are missed. First collector launch (PID 30644) failed; data starts 04:51:36.
- Builder tools (verify.py, lint) outputs were read, not re-run; EasyEDA was never inspected directly (bridge off-limits).
