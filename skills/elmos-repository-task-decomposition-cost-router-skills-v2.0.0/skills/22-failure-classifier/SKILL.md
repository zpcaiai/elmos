---
name: elmos-failure-classifier
version: 1.0.0
description: Classify execution/validation failure so Elmos knows whether to retry, repair context, escalate model or stop.
---

# Failure Classifier

Classify execution/validation failure so Elmos knows whether to retry, repair context, escalate model or stop.

## Trigger conditions
- worker/validator failure

## Inputs
- `execution logs`
- `test output`
- `diff`

## Outputs
- `failure class`
- `recommended action`

## Procedure
1. Distinguish transient tool, formatting, localized test, semantic, integration, architecture, context loss, policy and budget failures.
2. Estimate whether same model can fix cheaply.
3. Emit promotion trigger when needed.

## Guardrails
- Policy/security violations are not ordinary retries.

## Acceptance criteria
- one actionable class selected with evidence

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
