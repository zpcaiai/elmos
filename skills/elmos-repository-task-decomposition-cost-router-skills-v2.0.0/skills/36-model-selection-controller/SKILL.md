---
name: elmos-model-selection-controller
version: 1.1.0
description: Expose Smart or user-selected execution model choices in the Elmos UI, validate the choice against the immutable 10-model allowlist, and enforce it consistently across routing, retry, fallback, review and audit records.
---

# Model Selection Controller

Provide a production-safe model-selection contract between the Elmos page, run API and repository orchestrator.

## Trigger conditions
- a repository run is created from the UI/API/CLI
- the user changes execution model preference before dispatch
- a resumed run restores its model-selection state

## Inputs
- `model_selection` conforming to `schemas/model-selection.schema.json`
- `config/model-registry.yaml`
- `config/model-selection-policy.yaml`
- `config/router-policy.yaml`
- current provider availability / quotas when available

## Outputs
- validated `model_selection.json`
- effective routing constraints for the run
- UI model catalog containing exactly Smart + the ten allowlisted models
- preflight warnings or blocking reasons
- auditable model-switch events

## User-facing modes

### 1. Smart — system intelligent selection
- Default and recommended mode.
- The user does not choose a fixed model.
- Elmos routes **each atomic task independently** using `elmos-cost-performance-router`.
- Default optimization is `cost_performance`: lowest expected completed-task cost subject to quality, risk, budget and deadline constraints.
- Optional UI profiles may expose `lowest_cost`, `max_quality`, and `fastest` without changing the 10-model allowlist.
- After decomposition, the page shows the chosen model for every task, estimated cost/ETA, runner-up, and routing reason.

### 2. Manual — user selects one model
- The page displays exactly the ten aliases in `config/model-registry.yaml`.
- The selected model is locked for **primary implementation calls**.
- The router does not silently replace the user's model merely because another model has a better score.
- Hard incompatibilities (disabled/unavailable model, context limit too small, required tool unsupported, hard quota failure) block preflight or trigger only the fallback behavior explicitly selected by the user.

#### Manual fallback policy
- `strict` (default): never switch the primary implementation model. If a capability failure requires another model, stop that task as `model_reselection_required` and surface it in the UI.
- `smart_within_allowlist`: after classified failure/hard incompatibility, the router may choose another model from the same ten-model allowlist. Every switch MUST record `from_model`, `to_model`, failure class, reason, estimated extra cost and timestamp.

#### Verification policy
- `system_required_verifiers` (default): the user's chosen model performs implementation, while mandatory independent review/certification gates may select another allowlisted verifier when policy requires it.
- `selected_model_only`: all model-based verification uses the selected model too. If an independent reviewer is mandatory (security/auth/payments/schema migration/concurrency/public breaking API/critical infrastructure), final certification must be marked conditional or blocked; it may not claim an unconditional production pass.

## Page requirements
1. Render a top-level segmented choice: `Smart` or `Choose model`.
2. Smart mode is shown first with a `Recommended` badge.
3. Manual mode renders ten model cards/select options from the backend catalog; never hard-code a different model list in the frontend.
4. Each model may show display name, availability, relative/live cost, latency class, context capacity, role/strength tags and quota state when data exists.
5. Disabled/unavailable models remain visible but cannot be selected; show the reason.
6. Manual mode shows an advanced toggle: `Allow intelligent fallback if this model fails` mapped to `smart_within_allowlist`.
7. Manual mode shows how verification works and must not imply that a mandatory independent verifier is the same as the execution model.
8. Before Start, show predicted model strategy, autonomous system ETA, estimated cost/credits and any certification limitations.
9. During execution, show per-task actual model, status, attempts and model-switch events.
10. On resume, restore the exact selection that created the run; do not silently reset to Smart.

## API contract
Recommended run payload:

```json
{
  "model_selection": {
    "mode": "smart",
    "selected_model": null,
    "optimization_profile": "cost_performance",
    "fallback_policy": "strict",
    "verification_policy": "system_required_verifiers",
    "selection_source": "ui",
    "locked_by_user": false
  }
}
```

Manual example:

```json
{
  "model_selection": {
    "mode": "manual",
    "selected_model": "kimi-k3-max",
    "fallback_policy": "smart_within_allowlist",
    "verification_policy": "system_required_verifiers",
    "selection_source": "ui",
    "locked_by_user": true
  }
}
```

## Procedure
1. Load the model catalog only from `config/model-registry.yaml`.
2. Validate payload against `schemas/model-selection.schema.json`.
3. Reject any unknown alias before run creation.
4. Resolve model enabled/availability/quota/context/tool requirements.
5. Persist `.elmos/runs/<run_id>/model-selection.json` before task dispatch.
6. In Smart mode, pass all eligible models to the cost/performance router.
7. In Manual mode, constrain primary execution to `selected_model` and pass fallback/verification policy to router and retry controller.
8. Persist every user change before execution. Once any model task has started, treat the run selection as immutable unless the run is explicitly paused and a policy-change event is recorded.
9. Emit structured `model_selection_resolved` and `model_switch` events into `events.jsonl`.
10. Include selected mode, selected model, actual model distribution and deviations/fallbacks in final certification/reporting.

## Guardrails
- Exactly ten selectable models; no provider adapter may inject an eleventh model.
- Manual selection cannot disable security, budget, path, migration, concurrency or deterministic gates.
- Never silently fall back in `strict` mode.
- Never claim independent review when the same selected model performed both implementation and review.
- Frontend model IDs must be logical aliases, not arbitrary provider IDs.
- UI labels/prices are presentation metadata; backend policy remains authoritative.

## Acceptance criteria
- Smart + exactly ten manual model options are visible from one backend source of truth.
- Unknown/disabled models cannot start a run.
- Smart mode demonstrably routes tasks independently.
- Manual strict mode uses the selected model for every primary implementation call or stops with an explicit reselection state.
- Manual fallback mode never switches outside the ten-model allowlist and records every switch.
- Resume restores model selection exactly.
- Final run report distinguishes user-selected, system-selected, fallback and verifier model usage.

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard`, this selection controller, and `elmos-cost-performance-router` unless the current skill is one of those controls.
- Return structured evidence rather than a prose-only completion claim.
