---
name: human-effort-estimator
description: Estimate human modernization effort as evidence-bounded ranges. Use for person-day/person-month estimates, confidence, assumptions, contingency or re-estimation gates.
---
# Human Effort Estimator

## Workflow
1. Estimate each DAG step from modules, findings, tests, APIs and sensitive subsystems.
2. Return minimum, likely and maximum person-days plus policy-defined person-month conversion.
3. State staffing and scope assumptions and evidence confidence.
4. Require re-estimation after baseline and dependency evidence changes.

## Acceptance
- Never output a single-point commitment.
- Minimum <= likely <= maximum.
- Low evidence produces wider ranges and low confidence.

