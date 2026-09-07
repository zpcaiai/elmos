---
name: automation-score-calculator
description: Estimate deterministic migration automation potential. Use for deciding OpenRewrite eligibility, test-backed automation, manual review burden or unattended-execution policy.
---
# Automation Score Calculator

## Workflow
1. Start from explicit policy factors, not model confidence.
2. Reward deterministic build/test evidence and known recipe-eligible patterns.
3. Penalize public contracts, architecture risk, custom plugins and missing tests.
4. Emit a 0-100 score with factor map and rationale.

## Acceptance
- A high score does not authorize execution.
- Unknown evidence cannot increase automation.
- Factor changes are reviewable between plan revisions.

