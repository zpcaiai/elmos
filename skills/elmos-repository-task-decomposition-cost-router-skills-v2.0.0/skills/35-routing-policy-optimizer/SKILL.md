---
name: elmos-routing-policy-optimizer
version: 1.0.0
description: Periodically optimize thresholds, tier ordering and escalation rules from telemetry while preserving safety constraints and the ten-model allowlist.
---

# Routing Policy Optimizer

Periodically optimize thresholds, tier ordering and escalation rules from telemetry while preserving safety constraints and the ten-model allowlist.

## Trigger conditions
- sufficient telemetry or scheduled tuning

## Inputs
- `historical telemetry`
- `current policy`
- `budget goals`

## Outputs
- `candidate policy`
- `offline evaluation`
- `approved policy`

## Procedure
1. Backtest candidate routes against historical tasks.
2. Compare cost, first-pass success, total completion cost, latency and escaped defects.
3. Reject regressions in critical-task quality.
4. Canary new policy on low-risk tasks.

## Guardrails
- Cannot add an 11th model.
- Cannot lower mandatory high-risk tier without explicit policy change.

## Acceptance criteria
- candidate shows measurable expected-cost improvement without quality regression

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
