# Getting Started with DESK

This guide walks you through installation, your first hardware project, and monitoring execution via local Mission Control.

---

## 1. Prerequisites

- **Python:** Version 3.9 or higher (Python 3.11/3.12 recommended).
- **Git:** Installed and available on system PATH.
- **Operating System:** Windows 10/11, macOS, or Linux/Ubuntu.
- **Optional ECAD:** EasyEDA Pro (desktop client or web bridge) or KiCad 7/8.

---

## 2. Installation

Clone the repository and verify your installation:

```bash
git clone https://github.com/NijoP/DESK.git
cd DESK

# Verify core engineering test suite (zero external dependencies required)
python -m unittest discover -s tests -p "test_*.py"
```

Expected output:
```text
Ran 4xx tests in 20-30s
OK (skipped=3)
```
The exact count grows with every release; what matters is `OK` with zero failures and zero errors. The
three skips are live-only checks (bridge port discovery, optional CLIs).

---

## 3. Launch Local Mission Control

Start the local monitoring server and view real-time execution in your browser:

```bash
# Start dashboard and open default browser
python desk.py dashboard

# Or inspect formatted terminal status
python desk.py status
```

Open `http://127.0.0.1:49620` to access the Mission Control room.

---

## 4. Run an Engineering Project

### Initialize a Project:
```bash
python tools/new_project.py MY_PRODUCT
```

### Review Client Requirements:
Inspect `projects/MY_PRODUCT/REQUIREMENTS.md` and verify the power budget, voltage tree, and physical envelope.

### Execute Engineering Blocks:
```bash
# 1. Lint block specification
python tools/lint.py projects/MY_PRODUCT 01_POWER_SUPPLY

# 2. Build schematic commands
python tools/build.py projects/MY_PRODUCT 01_POWER_SUPPLY

# 3. Verify netlist and pin correctness
python tools/verify.py projects/MY_PRODUCT 01_POWER_SUPPLY
```

### Route the PCB:
```bash
python tools/route.py projects/MY_PRODUCT --passes 30
```

Watch the Mission Control dashboard update live as nets are routed, planes are poured, and 8 fail-closed quality gates are audited.
