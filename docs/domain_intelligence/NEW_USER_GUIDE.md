# Domain intelligence: new-user guide

DESK understands what kind of board you are building before it designs anything. Describe the product; DESK names the archetype, the engineering overlays, the component roles it expects, the rules it will enforce, and what it still needs from you.

## 1. See what DESK knows

```bash
python tools/desk.py domains list                       # 14 domains, 100 archetypes
python tools/desk.py domains search "wireless battery sensor"
python tools/desk.py domains show lora_transceiver      # purpose, required roles, critical constraints, rules
python tools/desk.py domains check                      # library consistency (schemas, references, evaluators)
```

## 2. Classify your requirement

```bash
python tools/desk.py domains classify "24 V input motor controller with a 3-phase BLDC motor, 10 A peak current, ESP32 control and CAN communication"
```

Output: primary archetype, secondary archetypes, overlays, component families, the evidence for the decision, conflicts and the information still missing. Status `REVIEW_REQUIRED` means DESK will not proceed on its own: typically mains or HV ambiguity, or two close candidates.

Structured input is better than prose. A JSON file with declared values avoids extraction guesses:

```json
{"text": "3-phase BLDC controller", "voltage_rails": {"VBUS": 24.0, "3V3": 3.3}, "current_limits_A": {"VBUS": 10.0, "3V3": 0.6},
 "peak_current_a": 10.0, "continuous_current_a": 6.0, "fet_id_rating_a": 30.0, "protocols": ["can"]}
```

```bash
python tools/desk.py domains validate requirements.json --project projects/MYBOARD
```

`validate` classifies, composes the rules, builds a DesignProfile from your declared values only, evaluates every rule and prints PASS/FAIL per rule with BLOCKING issues first. Exit code 0 means READY.

## 3. Read the rules before layout

```bash
python tools/desk.py domains rules buck_converter --overlays switching_power,high_current
```

Each rule shows its severity, whether DESK ENFORCES it (and in which subsystem), ADVISES it, or cannot evaluate it (UNSUPPORTED), its evidence state and its standards references. Advisory and unsupported rules are your review list.

## 4. Use the compiled profile

The JSON printed by `validate --json` contains `compiled.design_profile`: save it as `projects/<P>/design_profile.json` (or merge into an existing one) and the existing tools apply it: `tools/route.py` sizes widths and clearances from it and stops on blocking issues; the copper engine and power planner read it; the agent loop can call `classify_requirements` and `domain_rules`.

## 5. What DESK will not do

* Guess a current, a voltage, a pin map or a part. Missing inputs block (`fail-closed`).
* Treat a mains board like a 3.3 V board: the mains overlay is added whenever mains is detected and a human must confirm.
* Claim a rule is enforced when no subsystem applies it: such rules are listed as ADVISORY or UNSUPPORTED.
* Certify IPC/IEC values: table transcriptions are marked unverified until a human check.

## 6. Adding knowledge

Edit the JSON under `library/pcb_domains/` (archetypes, overlays, families, rule sets, references), keep ids unique, cite a reference for every BLOCKING rule, choose an honest `status`, then run `python tools/desk.py domains check` and the test suite. Regenerate `docs/domain_intelligence/TAXONOMY_REFERENCE.md`, `COMPONENT_FAMILY_REFERENCE.md` and `RULE_CATALOGUE.md` from the data.
