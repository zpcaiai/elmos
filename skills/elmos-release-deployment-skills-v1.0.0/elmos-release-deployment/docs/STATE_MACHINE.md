# Deployment state machine

```text
REQUESTED
  -> POLICY_CHECKED
  -> PREFLIGHT
  -> LEASED
  -> ARTIFACT_RESOLVED
  -> MIGRATION_PREFLIGHT
  -> DEPLOYING
  -> RUNTIME_HEALTH
  -> SMOKE_VERIFY
  -> TRAFFIC_PROMOTION
  -> EVIDENCE_COMMIT
  -> SUCCEEDED
```

Failure branches:

```text
(any pre-mutation failure) -> REJECTED / FAILED_NO_MUTATION
(any post-mutation failure) -> FAILED -> ROLLBACK_PLANNED
ROLLBACK_PLANNED -> ROLLING_BACK -> ROLLBACK_VERIFY -> ROLLED_BACK
ROLLBACK_VERIFY failure -> FAILED_NEEDS_HUMAN
unsafe/unknown DB state -> FAILED_NEEDS_HUMAN
```

## Recovery invariant

On restart, workflow must derive the next safe action from persisted state plus remote observation. It must never blindly re-run a side effect.

## Idempotency examples

- registry resolve: `(deployment_id, artifact_name)`
- remote bootstrap: `(deployment_id, target_id, step_version)`
- container switch: `(deployment_id, target_id, desired_digest)`
- traffic change: `(deployment_id, route_id, desired_backend_set)`
- evidence commit: `(deployment_id, evidence_version)`
