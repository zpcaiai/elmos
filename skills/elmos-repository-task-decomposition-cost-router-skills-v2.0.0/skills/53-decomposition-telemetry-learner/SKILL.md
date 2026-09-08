---
name: elmos-decomposition-telemetry-learner
version: 2.0.0
description: Learn repository- and task-family-specific decomposition priors from execution, replans, integration failures and final certification.
---

# Decomposition Telemetry Learner

Improve how Elmos decomposes future work from its own outcomes.

## Inputs
- task execution telemetry
- plan revisions
- integration conflicts
- verifier results
- final certification outcome

## Outputs
- `decomposition priors`
- `granularity calibration`
- `seam quality statistics`
- `replan predictors`

## Procedure
1. Measure first-pass success, replan rate, hidden dependency discovery, split/merge-after-start, context overflow and integration conflicts.
2. Aggregate by repository, task family, architecture region, harness and model tier.
3. Learn which seams and task sizes minimize completed-task cost and defect escape.
4. Decay observations after major repository architecture or tooling changes.
5. Feed calibrated priors into granularity, impact and scheduling decisions.

## Guardrails
- Do not optimize solely for fewer tasks or fewer tokens.
- Final repository acceptance and keep/revert outcomes outweigh self-reported model success.

## Acceptance criteria
- learned policy is versioned, replayable and can be disabled to restore deterministic defaults

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
