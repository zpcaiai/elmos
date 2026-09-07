# Model Selection UI & Runtime Contract

## Goal
Allow a user to start any repository-level Elmos run in either **Smart** mode or with one explicitly chosen model from the immutable ten-model allowlist, while preserving auditability and repository-level safety gates.

## Primary UX

```text
Execution model

[ Smart — Best value per task  Recommended ]
  Elmos chooses a model independently for each decomposed task.

[ Choose model ]
  ○ GPT-5.6 Sol Max
  ○ Claude Opus 5 Max
  ○ Claude Fable 5
  ○ Grok 4.6
  ○ Kimi K3 Max
  ○ GLM-5.3 Max
  ○ Qwen3.8-Max
  ○ DeepSeek V4 Pro 0813
  ○ Gemini 3.7 Flash High
  ○ Claude Sonnet 5

  [ ] Allow intelligent fallback if this model fails
```

The frontend MUST obtain the model list from the backend registry endpoint/source; this text is illustrative, not a second source of truth.

## Smart mode
Smart mode operates at atomic-task granularity. Two tasks in the same repository run may intentionally use different models. The UI should show the post-decomposition assignment plan and update it if a retry/escalation changes the effective model.

## Manual mode
Manual selection controls primary implementation calls. Default fallback is strict. Mandatory independent verification may still use another allowlisted verifier under `system_required_verifiers`, which should be explained before execution.

## Suggested API shapes

### GET model catalog
Return exactly the ten aliases with server-side metadata:

```json
{
  "selection_modes": ["smart", "manual"],
  "default_mode": "smart",
  "models": [
    {
      "alias": "kimi-k3-max",
      "display_name": "Kimi K3 Max",
      "enabled": true,
      "available": true,
      "relative_cost_tier": 2,
      "role_hint": "long_context_worker"
    }
  ]
}
```

### POST create run
Use `model_selection` from `schemas/model-selection.schema.json`.

## State transitions
- `draft`: selection can change freely.
- `preflight`: selection is validated and estimates refreshed.
- `running`: selection is immutable unless explicitly paused and changed with an audit event.
- `paused_for_model_reselection`: manual strict mode could not continue with the selected model.
- `completed`: report selected and actual models separately.

## Audit events
At minimum persist:
- `model_selection_resolved`
- `model_selection_changed`
- `model_preflight_blocked`
- `model_switch`
- `manual_model_reselection_required`

## Test matrix
1. Smart selection returns no `selected_model` and routes at least two distinct task classes independently when policy scores differ.
2. Each of the ten manual aliases is accepted when enabled.
3. An eleventh/unknown alias is rejected at API validation.
4. Disabled/unavailable model cannot start in strict manual mode.
5. Manual strict failure never triggers another model.
6. Manual fallback failure may switch only to an allowlisted alias and emits event evidence.
7. Resume preserves model mode and selected model.
8. High-risk independent-review policy remains enforceable in manual mode.
9. UI and backend lists cannot drift because frontend consumes backend catalog.
10. Final report reconciles planned versus actual model use and cost.
