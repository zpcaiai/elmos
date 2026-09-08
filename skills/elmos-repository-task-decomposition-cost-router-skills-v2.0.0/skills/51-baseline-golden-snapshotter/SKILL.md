---
name: elmos-baseline-golden-snapshotter
version: 2.0.0
description: Capture repository behavior and build/test baselines before change so decomposition and final verification can detect unintended regressions.
---

# Baseline & Golden Snapshotter

Capture what must remain true before implementation begins.

## Inputs
- impacted scenarios
- repository graph
- available test/build commands

## Outputs
- `baseline evidence`
- `golden outputs`
- `known failing tests`
- `environment fingerprint`

## Procedure
1. Run scoped baseline builds/tests and record pre-existing failures.
2. Capture stable API responses, schemas, generated artifacts or traces when useful.
3. Fingerprint toolchain/environment so post-change failures are comparable.
4. Attach baseline evidence to relevant proof obligations.
5. Use differential validation after each integration checkpoint.

## Guardrails
- Never attribute a pre-existing failure to a new patch without differential evidence.

## Acceptance criteria
- impacted high-risk surfaces have a before/after comparison path

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
