---
name: elmos-cost-performance-router
version: 1.1.0
description: Choose the model with the lowest expected completed-task cost subject to quality, risk, budget and deadline constraints.
---

# Cost/Performance Router

Choose the model with the lowest expected completed-task cost subject to quality, risk, budget and deadline constraints.

## Trigger conditions
- task complexity/risk/context ready

## Inputs
- `task profile`
- `capability matrix`
- `live/normalized pricing`
- `budget`
- `model_selection`

## Outputs
- `ranked model candidates`
- `chosen model`
- `routing explanation`

## Procedure
1. Resolve `model_selection` first.
2. If mode is `manual`, lock primary implementation to `selected_model`; validate hard compatibility and do not score-replace it.
3. If mode is `smart`, apply risk minimum tier, then score all eligible allowlisted models.
4. Estimate invocation cost from context/output/tool cycles.
5. Estimate p_success and escalation cost.
6. Add integration-risk and latency penalties.
7. Rank eligible models by route score.
8. Prefer cheaper model only when expected completion cost remains lower.
9. On manual fallback, switch only when `fallback_policy=smart_within_allowlist` and record the switch reason/evidence.

## Guardrails
- Never select outside allowlist.
- Never let missing pricing silently mean zero cost.
- Never silently override a manual strict model choice.
- Risk tiers constrain Smart routing; manual mode reports risk mismatch and relies on universal gates/verification unless the chosen model is technically incompatible.

## Acceptance criteria
- selection is reproducible from inputs
- runner records runner-up and reason

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
