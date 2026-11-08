---
name: scout-task-intake
description: Intake and delegation for read-only Scout Tasks conducting reconnaissance, calculations, and audits without side effects.
triggers:
  - "scout"
  - "investigate"
  - "audit"
  - "query"
  - "explain"
  - "inspect"
inputs:
  user_intent: string
  scope: string
outputs:
  intelligence_report: dict
  markdown_report_path: string
authoritative_pipeline: M0
replay_safety: SAFE_READ
---

# Scout Task Intake Skill

## Purpose
Prepares and executes non-mutating investigations, physical audits, and clearance queries.

## Procedural Execution Checklist

1. **Zero-Mutation Enforcement**:
   - Verify that the task requires no canvas or file modifications.
   - Enforce read-only adapter mode (no writer lock required).
2. **Reconnaissance Execution**:
   - Query PCB snapshot, netlist database, or IPC calculator.
   - Run diagnostics without creating or deleting primitives.
3. **Intelligence Report Generation**:
   - Compile findings into structured Markdown.
   - Present concise brief to Captain on the Bridge.
