# Failure Taxonomy

Every failed step MUST be classified.

- `TRANSIENT_PROVIDER` — retry may succeed.
- `QUOTA_PROVIDER` — requires fallback/cooldown/budget action.
- `INFRASTRUCTURE` — worker/network/storage/runtime failure.
- `STALE_STATE` — revision/anchor/lease/fence no longer valid.
- `POLICY` — invariant or authorization rejection.
- `SEMANTIC` — transformation meaning is invalid.
- `COMPILE` — compiler/typecheck failure.
- `TEST` — test/contract/regression failure.
- `RUNTIME_EQUIVALENCE` — source/target behavior mismatch.
- `SECURITY` — security gate failure.
- `PERFORMANCE` — unacceptable nonfunctional regression.
- `MERGE_CONFLICT` — incompatible sibling changes.
- `INSUFFICIENT_EVIDENCE` — cannot prove required claim.
- `USER_CANCELLED`
- `UNKNOWN`

Retry policy MUST be keyed to failure class. `SEMANTIC`, `POLICY`, and `INSUFFICIENT_EVIDENCE` MUST NOT enter blind retry loops.
