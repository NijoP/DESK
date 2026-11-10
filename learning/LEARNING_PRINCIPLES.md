# DESK Learning Principles

These principles govern how DESK converts engineering experience into reusable knowledge.

## 1. Evidence Over Confidence

Never replace missing engineering evidence with AI confidence.
Every incident must be documented with actual error messages, API responses, and observed behaviour.
Hypotheses must be clearly marked as such.

## 2. Root Cause Before Recovery

Do not repeatedly retry failed operations without understanding why they failed.
Set sensible retry limits (max 2-3 attempts).
Change the recovery strategy when evidence shows the original approach is not working.
Distinguish slow execution from genuine deadlock or failure.

## 3. Cumulative Knowledge

The learning repository only grows. Never delete or overwrite previous incidents or lessons.
If a lesson becomes outdated, mark it as superseded and document why.
Link replacement lessons to the originals.

## 4. Engineering Maturity

Behave like an experienced human engineer:
- Remember previous mistakes
- Recognise familiar failure patterns
- Question incorrect assumptions
- Investigate root causes
- Verify fixes before trusting them
- Improve working procedures
- Share useful knowledge

## 5. Prevention Over Documentation

An incident report alone is insufficient.
Every significant incident must produce:
- A reusable lesson
- A preventive rule or procedure
- An update to the known failure index

## 6. Real-Time Learning

Document during execution, not after.
Maintain a session log for every engineering task.
Record: intended operation, actual result, unexpected behaviour, recovery attempt, verification.

## 7. Scope of Learning

Document incidents that:
- Waste significant execution time
- Risk engineering integrity
- Reveal incorrect assumptions
- Expose API incompatibilities
- Produce manufacturing defects
- Violate electrical connectivity
- Cause DRC failures

Do not document trivial typos or self-corrected minor errors.

## 8. Classification Accuracy

Root causes must be honestly classified:
- Incorrect assumption
- Missing documentation
- API incompatibility
- Implementation defect
- Engineering mistake
- Validation failure
- Environmental problem
- Resource/performance limitation
- Unknown cause

Do not invent a root cause. Mark uncertain conclusions as hypotheses.

## 9. Verification Required

Every recovery must be verified.
Record the evidence that the solution actually worked.
Do not assume a fix is correct because the error message disappeared.

## 10. Cross-Reference Discipline

Maintain indices with accurate cross-references.
Avoid duplicate incident IDs.
Preserve chronological history.
Make entries searchable by subsystem, error type, and resolution.