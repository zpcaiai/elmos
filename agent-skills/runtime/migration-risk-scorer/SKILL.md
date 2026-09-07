---
name: migration-risk-scorer
description: Compute explainable migration risk from ELMOS health evidence. Use for vulnerability, architecture, API, data, module, test or uncertainty risk scoring.
---
# Migration Risk Scorer

## Workflow
1. Score named factors from immutable health findings.
2. Increase risk for unknown evidence rather than treating it as zero.
3. Cap the aggregate score and preserve factor contributions.
4. Keep organization policy thresholds outside the raw score.

## Acceptance
- Same evidence gives the same score.
- Critical vulnerabilities and missing baseline evidence are visible factors.
- The score never replaces human approval for sensitive changes.

