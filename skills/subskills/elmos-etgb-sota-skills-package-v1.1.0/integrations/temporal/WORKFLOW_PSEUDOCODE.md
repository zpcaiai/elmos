# Temporal-style workflow contract

```text
ETGBRunWorkflow(run_id, plan_digest, candidate_digest)
  validate immutable candidate/plan
  acquire executor lease + fencing token
  reserve tokens/credits/wall-clock
  for shard in stable_shards:
    execute child CaseShardWorkflow with max account concurrency = 3
  aggregate Oracle, stability, mutation, cost and evidence
  seal evidence manifest
  evaluate hard release gates
  publish decision through transactional outbox
```

Every activity receives `run_id`, `case_run_id`, `idempotency_key`, `owner_id`, `fencing_token`, `candidate_digest`, `plan_digest`, and the prior checkpoint digest. Heartbeats carry phase progress and machine ETA. Cancellation runs compensation and preserves evidence. Resume is rejected when candidate, plan, authority, workspace, or checkpoint digests are incompatible.

Recommended retry policy:

- transient provider/network/preemption: bounded exponential retry;
- build/test/semantic/security failure: no retry until a new candidate exists;
- activity start-to-close timeout: phase-specific;
- workflow execution timeout: budget-driven, with checkpoint-and-pause before expiry.
