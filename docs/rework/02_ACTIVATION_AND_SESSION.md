# DESK Rework Mode: Activation & Session Lifecycle

**Document ID:** `docs/rework/02_ACTIVATION_AND_SESSION.md`  

---

## 1. Natural-Language Activation

Engineers interact with DESK through PyAgent or supported AI coding agents. Natural-language intents recognized include:

- `"Activate Rework Mode."`
- `"I want to rework an existing PCB."`
- `"Continue my unfinished EasyEDA project."`
- `"Take this PCB to manufacturing readiness."`
- `"Audit this existing project and tell me what remains."`

The agent acknowledges the intent, enters Rework Mode, and defaults to `AUDIT_ONLY` mode until explicit approval is granted.

---

## 2. Command-Line Activation

Engineers can also operate Rework Mode directly via the DESK CLI:

```bash
# Start a rework session
python tools/desk.py rework start projects/WATCH [--policy audit_only|guided|supervised]

# Check active rework session status
python tools/desk.py rework status projects/WATCH

# Run the 8-domain engineering audit
python tools/desk.py rework audit projects/WATCH

# View the prioritized surgical repair plan
python tools/desk.py rework plan projects/WATCH

# View discovered issues
python tools/desk.py rework issues projects/WATCH

# Approve a specific surgical repair
python tools/desk.py rework approve projects/WATCH RP-0001

# Execute an approved surgical repair
python tools/desk.py rework execute projects/WATCH RP-0001

# Generate the final manufacturing readiness report
python tools/desk.py rework report projects/WATCH
```

---

## 3. Session Lifecycle State Machine

```text
IDLE
  |
REWORK_REQUESTED
  |
INTAKE
  |
CONNECTING
  |
IDENTITY_CONFIRMATION
  |
BASELINE_CAPTURE
  |
ENGINEERING_AUDIT
  |
ISSUE_REVIEW
  |
REPAIR_PLANNING
  |
AWAITING_APPROVAL
  |
REPAIR_EXECUTION
  |
READBACK
  |
VERIFICATION
  |
RELEASE_ASSESSMENT
  |
[COMPLETED / NEEDS_REVIEW / NOT_READY / INTERRUPTED / CANCELLED]
```

Sessions persist atomically under `projects/<P>/state/rework/<SESSION_ID>/session.json` and survive process terminations.
