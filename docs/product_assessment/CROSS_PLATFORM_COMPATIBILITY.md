# Cross-Platform Compatibility and Resource Requirements

DESK's engineering core is standard-library Python with no GPU dependency. External pieces: EasyEDA Pro (desktop or browser) with the API Gateway, Node.js for the bridge server, Java for Freerouting, optional model CLIs (`pi`, `agy`) and remote model endpoints.

## Verified today

| Environment | State |
|---|---|
| Windows 11, Python 3.11, Java 23, Node 24, EasyEDA Pro 3.2.149 | the only tested environment; all 409 offline tests run here; doctor reports 0 failures |
| Linux / macOS | untested in this programme; code paths exist (POSIX credential store, `os.kill` liveness, `/tmp` config path) |

## Resource tiers (from `desk/runtime/resource_profile.py`, measured on this machine: tier LOW)

| Tier | Target machine | DESK behaviour |
|---|---|---|
| ENTRY | 2 cores, ≤ 8 GB, integrated graphics, no local AI | deterministic engines run in milliseconds; Freerouting 1 thread (`-mt 1`); model calls remote (`DESK_PROVIDER_ORDER=nvidia,...`); no local model |
| STANDARD | 4-8 cores, 16 GB | Freerouting threads = cores − 1 allowed; parallel L3 review |
| WORKSTATION | ≥ 8 cores, ≥ 32 GB | same, plus parallel benchmark runs |

Measured footprints: Mission Control server 50 MB RSS; Freerouting 2.1.0 on WATCH reached the JVM's 1.2 GB cap (`JAVA_TOOL_OPTIONS=-Xmx1200m` observed); dense-board analysis < 100 ms and < 50 MB.

## Platform-specific items

| Item | Windows | Linux | macOS |
|---|---|---|---|
| Credential vault | Credential Manager (tested) | 0600 file with obfuscation (untested live) | Keychain via `security` (secret visible in argv, SW-12) |
| Process liveness | `OpenProcess` (ctypes failure → assumed alive, 30-min lock risk) | `os.kill(pid, 0)` | same as Linux |
| Freerouting global config | `%TEMP%\freerouting\freerouting.json` | `$TMPDIR` or `/tmp/freerouting/freerouting.json` (path assumed, unverified) | same |
| Console encoding | UTF-8 forced in adapters (cp1252 bug fixed) | n/a | n/a |
| EasyEDA Pro availability | desktop + web | web (desktop Linux build exists; gateway untested) | desktop + web |

## Minimum requirements (provisional, to be confirmed by testing on an entry laptop)

Python 3.9+, 2 cores, 4 GB free RAM for Python + 1.5 GB for Java, Node 18+, Java 17+ for Freerouting 2.1 or Java 25 for 2.2+, network access for remote models and LCSC/JLCPCB data.

## Open items

CP-01 run the offline suite on Linux and macOS in CI (QA-06); CP-02 verify the Freerouting config path on POSIX; CP-03 measure an entry laptop end-to-end; CP-04 remove the `JAVA_TOOL_OPTIONS` dependence by passing `-Xmx` explicitly per tier.
