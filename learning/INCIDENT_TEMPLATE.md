# Incident Report Template

Copy this template to create a new incident report in `learning/incidents/`.

---

## INCIDENT-ID
**Format:** `INC-YYYYMMDD-NNN`
**Example:** `INC-20251111-001`

## Metadata
- **Date/Time:** YYYY-MM-DD HH:MM UTC
- **Project/Task:** [Project name or task description]
- **Subsystem:** [e.g., easyeda-integration, pcb-panelisation, copper-engine, drc-validation]
- **Severity:** [CRITICAL / HIGH / MEDIUM / LOW]
- **Status:** [OPEN / INVESTIGATING / RECOVERED / VERIFIED / CLOSED]

---

## Context
**What were you trying to accomplish?**
[Describe the engineering objective and the specific operation being attempted.]

---

## Expected Behaviour
**What should have happened?**
[Describe the correct/expected outcome based on documentation, API specification, or engineering principles.]

---

## Actual Behaviour
**What actually happened?**
[Describe the observed failure, incorrect result, or unexpected behaviour.]

---

## Error Evidence
**Exact error messages, API responses, terminal output, or observed behaviour:**

```
[Paste exact error messages here. Sanitize any sensitive data.]
```

**Relevant commands/parameters (sanitized):**
```bash
[Commands that led to the error]
```

**API call details (if applicable):**
```json
{
  "method": "API method name",
  "parameters": "sanitized parameters",
  "response": "error response"
}
```

---

## Root Cause Analysis

### Identified Cause
[Describe the actual root cause discovered through investigation.]

### Classification
- [ ] Incorrect assumption
- [ ] Missing documentation
- [ ] API incompatibility
- [ ] Implementation defect
- [ ] Engineering mistake
- [ ] Validation failure
- [ ] Environmental problem
- [ ] Resource/performance limitation
- [ ] Unknown cause (hypothesis: [describe])

### Why the Original Approach Failed
[Explain the specific mechanism of failure.]

---

## Recovery

### Attempts Made
| Attempt | Action | Result |
|---------|--------|--------|
| 1 | [Description] | [SUCCESS / FAILED / PARTIAL] |
| 2 | [Description] | [SUCCESS / FAILED / PARTIAL] |
| 3 | [Description] | [SUCCESS / FAILED / PARTIAL] |

### Successful Solution
[Describe the solution that worked.]

### Verification Evidence
[How was the fix verified? Include test results, DRC passes, visual inspection, etc.]

---

## Engineering Learning

### What This Failure Taught You
[Key insight gained.]

### Why Original Approach Failed
[Deeper understanding of the failure mechanism.]

### What Should Have Been Done Differently
[Correct approach with hindsight.]

### Missing Information
[What information would have prevented this?]

### Early Warning Signs
[What could have identified this problem earlier?]

### Future Prevention
[How DESK can avoid this in future projects.]

---

## Prevention Strategy

### Preventive Rule/Procedure
[Concrete, actionable preventive measure.]

### Implementation
[How to implement this prevention in DESK workflows.]

---

## Reusability

### Applicable Future Tasks
[List task types that can benefit from this knowledge.]

### Related Subsystems
[Which DESK subsystems should incorporate this learning?]

---

## Cross-References
- **Related Incidents:** [INC-XXXXXX-XXX, ...]
- **Generated Lessons:** [LSN-XXXXXX-XXX, ...]
- **Known Failure Pattern:** [KF-XXXXXX-XXX or N/A]

---

## Changelog
- YYYY-MM-DD: Incident created
- YYYY-MM-DD: Root cause identified
- YYYY-MM-DD: Recovery verified
- YYYY-MM-DD: Incident closed