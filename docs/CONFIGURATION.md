# Configuration reference

Generated from `desk/config.py` SCHEMA (`python desk.py config schema`). Precedence: environment variable, then `~/.desk/config.json` (or `DESK_CONFIG_FILE`), then `desk.config.json` at the repository root, then the default. Files are flat JSON objects keyed by variable name. Secrets are refused in the repository file. `python desk.py config show` prints the effective values with their source and masks secrets; `python desk.py doctor` validates them.

| Key | Type | Default | Group | Description |
|---|---|---|---|---|
| `DESK_PROJECT` | path |  | project | Project directory used when a CLI gets no explicit path. |
| `EDA_PORT` | int |  | bridge | EasyEDA Pro API-gateway port; unset = probe 49620-49629. |
| `EDA_WINDOW_ID` | str |  | bridge | EasyEDA window to target when project.json has none. |
| `EASYEDA_API_REF` | path |  | bridge | Alternative EasyEDA API reference file for tools/ctx.py api. |
| `DESK_TELEMETRY` | bool | 1 | project | Append tool runs to .desk_learn/runs.jsonl (0 disables). |
| `DESK_ALLOW_UNBOUND_WINDOW` | bool | 0 | safety | 1 lets a mutating bridge call run without a verified window binding (it then hits the ACTIVE window). Default 0 refuses (KF-20261112-008, UPS_1000 F-001). |
| `DESK_RELIABILITY_AUTORECOVER` | bool | 1 | safety | 0 turns the self-healing supervisor's AUTO recoveries into proposals only. |
| `DESK_FR_CHUNK_SAFETY` | float | 0.6 | routing | Fraction of a routing chunk's time window the adaptive planner fills with measured pass time (0.3-0.9). |
| `DESK_MUTATION_POLICY` | enum | record | safety | record: journal whether a human approval accompanied each live mutation; require: refuse non-idempotent mutations without one. |
| `DESK_CREDENTIAL_STORE` | enum |  | credentials | Force a vault backend instead of the platform default. |
| `NVIDIA_API_KEY` | secret |  | credentials | NVIDIA NIM key (or store it with desk.py auth configure). |
| `LCSC_CLIENT_ID` | str |  | credentials | LCSC API client id (live supplier calls). |
| `LCSC_CLIENT_SECRET` | secret |  | credentials | LCSC API client secret. |
| `DESK_MOCK_SUPPLIERS` | bool | 0 | credentials | 1 = supplier providers answer from offline fixtures. |
| `DESK_MOCK_MANUFACTURING` | bool | 0 | credentials | 1 = JLCPCB client answers from offline fixtures. |
| `DESK_DOMAIN_LIBRARY` | path |  | knowledge | Alternative library/pcb_domains root. |
| `DESK_JAVA` | path |  | routing | Java executable for Freerouting (else library/tools/jdk*/bin, else PATH). |
| `FREEROUTING_JAR` | path |  | routing | Explicit Freerouting JAR. |
| `FREEROUTING_BIN` | path |  | routing | Explicit native Freerouting executable. |
| `DESK_FR_STAGNATION_FLAG` | bool | 0 | routing | 1 = pass --router.autorouter.stagnation_pass_limit (rejected by Freerouting 2.5.0). |
| `DESK_DOCTOR_CACHE_TTL_S` | int | 86400 | routing | Seconds the doctor caches Java/Freerouting/Node probes. |
| `DESK_AGENT_MODEL` | str | nvidia/nemotron-3-ultra-550b-a55b | models | Model for desk.py agent. |
| `DESK_HTTP_BASE_URL` | str | https://integrate.api.nvidia.com/v1 | models | OpenAI-compatible endpoint. |
| `DESK_HTTP_API_KEY_ENV` | str | NVIDIA_API_KEY | models | Name of the variable holding the endpoint key. |
| `DESK_HTTP_MAX_TOKENS` | int | 2048 | models | max_tokens per HTTP completion. |
| `DESK_PI_PATH` | path |  | models | Pi CLI executable (else PATH). |
| `DESK_PI_EXTENSIONS` | bool | 0 | models | 1 = let Pi load its extensions (slower, more tokens). |
| `DESK_AGY_PATH` | path |  | models | Gemini CLI executable (else PATH). |
| `DESK_PROVIDER_ORDER` | str | agy,pi | models | Provider preference for L1/L2, comma separated. |
| `DESK_L3_PROVIDERS` | str | agy,pi | models | The two providers used for L3 dual review. |
| `DESK_FRONTIER_PROVIDER` | str |  | models | Provider for L4 (default: first of DESK_PROVIDER_ORDER). |
| `DESK_FRONTIER_MODEL` | str |  | models | Model id for L4 on that provider. |
| `DESK_L[1-4]_MODEL_(AGY|PI|NVIDIA)` | str |  | models | Model per tier and provider. |
| `DESK_L[1-4]_TIMEOUT` | float |  | models | Per-tier timeout in seconds (defaults 30/90/180/300). |
| `DESK_L[1-4]_THINKING` | enum |  | models | Per-tier thinking level. |
| `DESK_CONFIG_FILE` | path |  | project | User config file (default ~/.desk/config.json). |
| `DESK_WEFT_SERVICE_URL` | str |  | weft | DESK node service URL for Weft workflows (default http://127.0.0.1:<service.DEFAULT_PORT>). |
| `DESK_WEFT_TOKEN` | secret |  | weft | Bearer token for the node service (else the token file). |
| `DESK_WEFT_MODEL` | str |  | weft | Model for model-backed Weft nodes (falls back to DESK_AGENT_MODEL). |
| `DESK_WEFT_VALIDATOR` | path |  | weft | Path to the built Weft validator binary. |
| `DESK_WEFT_CHECKOUT` | path |  | weft | Pinned Weft checkout directory the compiler harness reads the catalog from. |
| `DESK_WEFT_PROJECTS_ROOT` | path |  | weft | Root directory Weft runs may touch. |
| `DESK_WEFT_DISPATCHER` | str | http://127.0.0.1:14111 | weft | Weft dispatcher address desk.py weft signals/answer talk to (the default install's). |
| `DESK_WEFT_SIGNAL_TOKEN` | secret |  | weft | Weft signal token (weft token mint) for listing and answering waiting approvals. |

Keys read directly from the environment and not yet routed through `desk.config`: `DESK_PI_PATH` and `DESK_PI_EXTENSIONS` in `desk/orchestrator/pi_adapter.py` (uncommitted change pending in another workstream) and the `DESK_WEFT_*` keys plus `NVIDIA_API_KEY`/`DESK_AGENT_MODEL` inside `desk/weft/` (merged 2026-11-12). `tests/test_config.py` lists these files as the only allowed exceptions.
