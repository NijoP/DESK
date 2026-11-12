# T+50 Report (T+50 = 05:40:28)
Written at wall 2026-11-12 ~05:41 +05:30 (about T+50.5). Slightly late versus the target, because it was triggered by the coordinator's checkpoint at ~05:40; snapshot 05:40:28.

## Stage status
- Stage 3 (routing, 90 min): started 05:31:00.9, elapsed ~9.4 min at snapshot, ~80.6 remaining, deadline 07:01:00. No routing has happened yet: pcb/routing/ does not exist and route_run_2.log is 0 bytes (created 05:40:13, router just launched).
- Overall elapsed ~49.9 min; remaining ~175.
- Of the first ~9 minutes of the routing budget, about 8 (05:32:39 failure to 05:40:13 re-run) went on the missing router and waiting for human approval. That time counts against Stage 3 under the no-borrowing rule.

## Failures, interventions (evidence: failures/failure_register.json, execution.jsonl, pcb/route_run_1.log)
- F-012 (route.py failed, no Freerouting engine): ACCEPT the root cause. route_run_1.log shows RuntimeError "No compatible Freerouting engine found in ...DESK\library\tools. Install a Java runtime matching the JAR (v2.2+ needs Java 25) or set FREEROUTING_JAR" from the smoke test; pre-flight itself passed (planes 0/0, 1 outline primitive, 0 pads in keep-outs). Caveat: this is a missing prerequisite in the benchmark environment that the setup stage did not catch (not a design error); the builder says it matches a pre-existing DESK test failure, which I have not verified. Whether ENVIRONMENT_SETUP.md should have provided the jar is a Founder question, not mine.
- H-002 (human intervention, Captain approved the download): evidence is real: environment/freerouting/freerouting-2.1.0.jar (66,978,394 bytes, mtime 05:39:50) and its SHA-256 recomputed by me = 2c07d58f75dac03782664081e7a58b41c25400d871a9fcf166a2ea6fe60d5def, matching the coordinator's value. I cannot verify that hash against the official release (no network inspection of the source); the builder says official. The jar sits outside the builder project in the environment folder. This is the third human intervention (H-0 window reconnect; H-001 Apply; H-002 install approval) and it is a dependency introduced mid-run. A Nemotron-comparison note: check whether Nemotron's run also lacked a router.
- Java: builder says OpenJDK 23 is installed, jar 2.1.0 is therefore usable (the 2.2+ Java 25 requirement does not apply). Not yet confirmed by a running router.

## New artifact: schematic/desk/design_profile.json (judged on evidence)
- It declares 2 layers, 74x44 mm, rails (VBUS/5V 5.25 V, 3V3 3.3 V) and current limits (VBUS/5V/GND 0.75 A, 3V3 0.6 A, LEDs 5 mA), the USB diff pair (90 ohm, 10 mil width, 6 mil spacing, max length diff 5 mm) and critical nets USB_DP/USB_DN/EN/GPIO0, with unknown_current_policy "fail".
- Consistency checks: 3V3 0.6 A equals the AP2112K rated output (600 mA); the 0.75 A on VBUS is consistent with a 0.5 A hold / 1 A trip polyfuse only loosely (limit is below the trip current but above the hold current, so a continuous 0.75 A would exceed the fuse hold rating; this is a design-intent number, not an error in routing). The 5.25 V rail value is the USB maximum, fine. 10 mil / 6 mil on a 2-layer 1.6 mm board does not give 90 ohm differential impedance (it would be around 150-160 ohm over a distant plane); the builder's design_parameters allow "approximate 90 ohm", so this will need an honest note at Stage 3 review. Not a failure yet.
- It is an input to routing rules, written after Stage 1; I treat it as builder-declared, not a frozen requirement.

## Acceptance status
- Stage 3 Must Pass gates: none met yet (nothing routed; no DRC; no routing record). Overall: Stage 1 plausibly MET with caveats, Stage 2 NOT fully met (see T+40).

## Hardware 05:31-05:39 (CSV 49 rows)
- CPU 59-75 % (peak 75.4 % at 05:33:44 with 4 MB/s disk reads). EasyEDA steady 40-42 % CPU, WS 2.0-2.45 GB. Claude Code CPU 0.6-1.5 %, WS 1.52-1.66 GB (small decrease). Java/python 0 at sample points (router not yet running).
- RAM available fell from 1.5 GB to 670-899 MB between 05:32:43 and 05:39:45 while EasyEDA and Claude working sets did not grow, so the pressure is from something I do not capture (page cache, other processes, Java smoke test at 05:32); not a new EasyEDA leak. Watch during routing: a Freerouting JVM will need RAM, and the lowest value was 579 MB at T+10.
- Disk: 92 MB/s read burst at 05:36:45 (unexplained; probably the 67 MB jar being written/read or antivirus scan) and a 5 MB/s write at 05:39:45. Net: 5.4 MB/s at 05:39:45 is the jar download (about 67 MB, consistent with the coordinator). C: free 162.3 -> 162.63 GB (no loss from the jar; it is under environment, on the same drive; free space rose, so other cleanup occurred).
- GPU idle 0 %/0 MB/46-48 C, expected with remote inference. Telemetry PID 33512 alive; frozen hashes verified unchanged earlier in this checkpoint chain.
