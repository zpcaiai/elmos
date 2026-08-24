# Cache Miss Reason Taxonomy

A miss response should contain one or more structured reasons:

- `NO_ENTRY`
- `SOURCE_DIGEST_CHANGED`
- `PUBLIC_INTERFACE_CHANGED`
- `DEPENDENCY_LOCK_CHANGED`
- `RULE_PACK_CHANGED`
- `STAGE_VERSION_CHANGED`
- `STAGE_CONTRACT_CHANGED`
- `TOOLCHAIN_CHANGED`
- `TARGET_PROFILE_CHANGED`
- `COMPILER_FLAGS_CHANGED`
- `DECLARED_ENVIRONMENT_CHANGED`
- `PROMPT_TEMPLATE_CHANGED`
- `MODEL_SNAPSHOT_CHANGED`
- `TOOL_OUTPUT_CHANGED`
- `FEATURE_FLAG_CHANGED`
- `SCHEMA_INCOMPATIBLE`
- `VALIDATION_TOO_LOW`
- `TRUST_NAMESPACE_MISMATCH`
- `TENANT_MISMATCH`
- `PROVENANCE_INVALID`
- `ENTRY_EXPIRED`
- `ENTRY_REVOKED`
- `ENTRY_QUARANTINED`
- `ARTIFACT_MISSING`
- `ARTIFACT_CORRUPT`
- `RESTORE_COST_EXCEEDS_RECOMPUTE`
- `POLICY_BYPASS`
- `NONDETERMINISTIC_STAGE`

Each reason should include the old and new dimension digest when disclosure policy permits, plus a human-readable explanation that excludes source code and secrets.

## v1.2.0 parity outcome taxonomy

Every cache layer emits one terminal `outcome` and one leaf `reason_code`.

- `HIT`: requested work was actually avoided and the result/observation passed required validation.
- `NECESSARY_MISS`: a legitimate identity, dependency, policy, TTL, or trust change requires execution.
- `UNEXPECTED_MISS`: the request was eligible and no legitimate invalidator explains the miss.
- `BYPASS`: policy deliberately chose recompute, for example restore cost exceeded recompute cost.
- `RESTORE_FAILURE`: metadata was found but verified restore failed.
- `LOOKUP_ERROR`: the cache could not make a reliable decision.

Required new leaf codes include:

```text
MODEL_CHANGED
EFFORT_CHANGED
TOOL_SCHEMA_CHANGED
PROMPT_SEGMENT_CHANGED
PREFIX_COMPATIBILITY_CHANGED
PROJECT_SNAPSHOT_CHANGED
PUBLIC_INTERFACE_CHANGED
LOCKFILE_CHANGED
ENVIRONMENT_CHANGED
TTL_EXPIRED
CACHE_EVICTED
WRONG_SHARD
WRONG_REPLICA
COLD_WORKER
SNAPSHOT_REVOKED
DIGEST_MISMATCH
NAMESPACE_MISMATCH
AUTHORIZATION_DENIED
RESTORE_MORE_EXPENSIVE_THAN_RECOMPUTE
PROVIDER_UNSUPPORTED
UNKNOWN_PROVIDER_OUTCOME
UNKNOWN_COORDINATOR_OUTCOME
```

`UNKNOWN_*` is never silently converted to a necessary miss; it consumes the unexpected-miss SLO budget.
