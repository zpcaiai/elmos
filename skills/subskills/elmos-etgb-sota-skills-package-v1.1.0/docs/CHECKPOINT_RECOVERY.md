# Checkpoint, pause, resume and recovery

## Checkpoint schema

Checkpoints include candidate, plan, Environment, workspace and artifact digests; phase/revision; fencing token; side-effect receipts; resume payload; and previous checkpoint digest. This prevents a resumed run from combining incompatible attempts.

## Side-effect receipt

Each external effect records service, operation, resource, idempotency key, request digest, response digest, committed state and compensation status. A worker checks receipts before retrying.

## Recovery matrix

Test failure at every phase boundary and before/after durable writes:

- executor/process kill;
- host reboot and lease expiry;
- PostgreSQL failover;
- object-store partial upload;
- outbox commit/publish gap;
- provider timeout/rate limit;
- disk full/OOM;
- cancellation and budget exhaustion.

## Resume rejection

Reject on candidate/plan/policy/Oracle/normalization/corpus/image drift, corrupt checkpoint chain, stale fence, missing artifact or unresolved non-idempotent side effect.

## Implementation

Use `etgb/checkpoint.py`, `etgb/state.py`, PostgreSQL run/checkpoint/transition tables and the `checkpoint-resume-recovery` Skill.
