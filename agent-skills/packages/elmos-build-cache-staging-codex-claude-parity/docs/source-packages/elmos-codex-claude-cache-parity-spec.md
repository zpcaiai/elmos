# ELMOS Codex/Claude-Class Cache Parity Specification

Version: 1.2.0  
Date: 2026-08-20  
Status: implementation and certification contract

## 1. Purpose

This specification upgrades ELMOS v1.1.0 from a high-quality build/artifact cache into a complete coding-agent cache architecture. The goal is to reach or approach Codex/Claude Code class cache behavior on explicitly defined warm workloads: the same project, stable model and tool profile, follow-up turns, small edits, repeated conversions, restart recovery, and unchanged environments.

It does **not** assert that Codex or Claude Code has one public universal hit percentage, and it does not promise 95–100% reuse for cold starts, new repositories, model changes, tool-schema changes, provider switches, major dependency upgrades, or intentionally uncacheable real-time input.

The package separates three concepts:

1. **Target** — the mandatory engineering SLO in this specification.
2. **Certified benchmark result** — a measured result on a pinned corpus, commit, configuration, provider profile, and platform.
3. **Production observation** — posted live data for a declared cohort and time range.

Only the second and third may be used as achieved results.

## 2. System model

```text
User task / repository / project generation request
        |
        v
Canonical Prompt Compiler ---> Provider Prompt Prefix Cache
        |
        +--> Append-only Repository Context Ledger
        |          |
        |          +--> Cache-preserving Context Checkpoints
        |
        v
Multi-layer Cache Coordinator
   |        |        |          |           |
   |        |        |          |           +--> Native build caches
   |        |        |          +--------------> Environment snapshots
   |        |        +-------------------------> Local/remote CAS
   |        +----------------------------------> Exact Action Cache
   +-------------------------------------------> Checkpoint/staged artifacts
        |
        v
Incremental conversion/generation DAG
        |
        +--> cache-aware worker/provider affinity
        +--> DAG next-use protection and prefetch
        +--> exact invalidation and miss diagnostics
        v
Compile / test / behavior validation / atomic publish
```

## 3. Why eviction algorithms alone are insufficient

SIEVE, S3-FIFO, W-TinyLFU, size-aware admission, GDSF, DAG next-use, and adaptive policy selection improve what remains in a finite cache. Coding-agent parity additionally depends on:

- byte-stable prompt prefixes;
- append-only conversation/repository context;
- provider-specific cache keys, breakpoints, TTL choices, and usage accounting;
- exact ActionKey reuse for deterministic stages;
- precise dependency/public-interface invalidation;
- environment and dependency snapshots;
- session, model-replica, worker, and cache-shard affinity;
- long-session compaction that preserves stable prefix value;
- singleflight and partial-hit DAG execution;
- miss causality, parity benchmarks, and automated rollback.

## 4. Cache layers and truth boundaries

| Layer | Identity | Reusable result | Exactness | Durable source of truth |
|---|---|---|---|---|
| Provider prompt cache | provider namespace + model + effort + tool schema + stable prefix | previously processed input prefix/KV blocks | exact prefix | provider runtime; never task truth |
| Repository context ledger | stream + sequence + snapshot/content digests | read/summarized context and staleness history | exact event lineage | PostgreSQL/event log + CAS |
| Exact Action Cache | canonical ActionKey | immutable validated stage result | exact inputs/config | metadata DB + CAS |
| Local/remote CAS | content digest | immutable AST/IR/code/build/test/checkpoint bytes | exact bytes | CAS |
| Environment snapshot | canonical environment key | toolchain/dependency/index layers | exact declared environment | CAS + snapshot metadata |
| Native build cache | tool-specific key | compiler/package outputs | tool-defined exactness | native store + provenance |
| Semantic reuse | semantic fingerprint/vector | candidate plan/patch/template | non-exact | candidate only; revalidation required |
| Staging/checkpoint | run/node/attempt/lease + digest | durable generated files and task state | exact state machine | journal/DB + CAS |

No prompt, semantic, learned, or affinity cache may authorize a result that fails ActionKey, digest, tenancy, provenance, validation-level, or staged-file state checks.

## 5. Canonical prompt layout

Logical order:

```text
GLOBAL_STABLE
  01 system policy
  02 safety and authorization policy
  03 stable tool definitions
  04 stable output schemas
  05 stable Skills and execution contract

PROJECT_STABLE
  06 repository architecture and stable project constraints
  07 framework/language conversion profile

  ===== provider cache breakpoint / stable-prefix boundary =====

SESSION_APPEND_ONLY
  08 task contract and user turns
  09 repository context ledger projections
  10 file/symbol read events and stale markers
  11 tool/build/test observations

TURN_VOLATILE
  12 current request
  13 current Git diff/change set
  14 newly retrieved files
  15 current tool outputs and real-time data
```

Canonicalization requirements:

- stable ordering for tools, Skills, schemas, maps, file/symbol summaries, and enums;
- canonical JSON with normalized Unicode, paths, line endings, and numbers;
- no timestamp, UUID, request ID, temporary path, host name, volatile counter, or nondeterministic filesystem order in stable segments;
- provider/model/effort/tool-schema/prefix compatibility partitioning;
- segment manifests and first-difference diagnostics for every unexpected miss;
- safety and correctness instructions are never removed for cache gains.

## 6. Append-only repository context

Every repository observation is bound to:

```text
tenant scope
repository identity
branch lineage
repository snapshot digest
file/symbol content or interface digest
ledger stream + sequence
source tool and authorization
freshness state
```

When a read file changes, ELMOS appends `CONTENT_CHANGED` and `CONTEXT_STALE`; it does not rewrite old conversation messages. Content is reread only when the current task requires it. Unread unrelated files do not invalidate prior context. Whole-repository reinjection is forbidden after initial indexing except for an explicit diagnostic/export mode.

## 7. Context compaction

Compaction is planned before hard context limits and normally occurs at a natural task/DAG boundary. A `ContextCheckpoint` retains:

- immutable task/user contract;
- repository snapshot and changed-file state;
- decisions and rationale;
- unresolved requirements/questions;
- pending approvals and side effects;
- run/DAG/checkpoint state;
- staged/generated artifacts;
- build/test/validation state;
- source-linked summaries and CAS references.

The new compatibility group is warmed and atomically adopted; the old checkpoint remains rollbackable. Provider prompt cache is never the only durable task state.

## 8. Environment snapshot identity

```text
EnvironmentSnapshotKey = SHA256(
    base_image_digest
  + normalized_setup_script_digest
  + normalized_maintenance_script_digest
  + lockfile_digests
  + package_manager_config_digest
  + compiler_sdk_toolchain_digests
  + platform_and_architecture
  + approved_environment_digest
  + secret_reference_version_digest
  + snapshot_schema_version
)
```

Secrets are mounted after restore and never embedded in reusable layers. Corrupt, revoked, vulnerable, expired, or policy-incompatible snapshots are quarantined. Restore may be bypassed when verified rebuild is faster or cheaper.

## 9. Affinity routing

Hard filters:

- tenant authorization and cache namespace;
- provider/model/effort/tool/prefix compatibility;
- language/platform/runtime compatibility;
- worker health and required capacity;
- trust and validation constraints.

Soft score:

```text
score =
    expected_prompt_prefix_saving
  + expected_environment_saving
  + expected_local_artifact_saving
  + DAG_next_use_value
  - queue_delay
  - transfer_and_restore_cost
  - failure_risk
  - fairness_debt
```

Rendezvous/consistent hashing creates stable primary/secondary choices; bounded-load and fairness rules can override locality. Failover may lose a cache hit but must not lose durable state or duplicate side effects.

## 10. Multi-layer reuse planner

The coordinator evaluates legal paths:

```text
1. Resume valid checkpoint / sealed staged artifacts
2. Reuse exact Action Result at required validation level
3. Restore local/remote CAS inputs and execute only invalidated DAG closure
4. Restore compatible environment snapshot and native caches
5. Use provider prompt-prefix cache for required model calls
6. Full clean execution
```

It may probe independent stores concurrently. Singleflight coalesces identical authorized work. The plan records predicted and realized lookup/restore/recompute cost. A hit is counted only when requested work is actually avoided.

## 11. Mandatory SLOs

These are release/certification gates for eligible defined workloads:

| Metric | Mandatory target |
|---|---:|
| Stable conversation eligible cached-token reuse after turn 3 | >= 90% |
| Unexpected full-prefix miss rate | <= 2% |
| Exact rerun compute-weighted Action reuse | >= 99% |
| Redundant model/compiler/test calls on validated exact rerun | 0 |
| <=1% file edit, public interfaces unchanged: weighted reuse | >= 90% |
| Implementation-only unnecessary downstream invalidation | <= 5% |
| Unchanged environment snapshot hit rate | >= 95% |
| Warm-start p95 reduction versus cold | >= 80% |
| Service restart sealed-artifact reuse | >= 99.9% |
| Stable same-project follow-up net wall-clock saved | >= 70% |
| Stable same-project model input cost saved | >= 80% |
| Long-session eligible cached-token reuse after planned compaction warmup | >= 80% |
| Accepted false hits | 0 |
| Cross-tenant hits | 0 |
| Corrupt objects executed | 0 |
| Under-validated cached result published | 0 |

A cohort floor may be stricter than the global target. A result does not pass merely because the global average passes.

## 12. Metric definitions

```text
eligible_cached_token_reuse =
  cache_read_input_tokens
  / eligible_stable_input_tokens

compute_weighted_action_reuse =
  sum(recompute_cost_of_exact_hits)
  / sum(recompute_cost_of_all_eligible_actions)

unnecessary_invalidation =
  recomputed_actions_not_in_expected_invalidation_closure
  / all_recomputed_actions

net_wall_clock_saved =
  (cold_control_wall_clock - cache_enabled_wall_clock)
  / cold_control_wall_clock

model_input_cost_saved =
  (uncached_control_input_cost - cache_enabled_input_cost)
  / uncached_control_input_cost
```

Recompute cost includes model input/output, CPU/GPU, compilation, tests, network, decompression, critical-path delay, and validation evidence. Object hit and byte hit remain secondary diagnostics.

## 13. Miss taxonomy

Every layer emits one terminal outcome:

```text
HIT
NECESSARY_MISS
UNEXPECTED_MISS
BYPASS
RESTORE_FAILURE
LOOKUP_ERROR
```

Required families:

```text
COLD_START
IDENTITY_CHANGED
  MODEL_CHANGED
  EFFORT_CHANGED
  TOOL_SCHEMA_CHANGED
  PROMPT_SEGMENT_CHANGED
  PROJECT_SNAPSHOT_CHANGED
  PUBLIC_INTERFACE_CHANGED
  RULE_PACK_CHANGED
  LOCKFILE_CHANGED
  ENVIRONMENT_CHANGED
TTL_OR_RETENTION
  TTL_EXPIRED
  CACHE_EVICTED
PLACEMENT
  WRONG_SHARD
  WRONG_REPLICA
  COLD_WORKER
RESTORE
  OBJECT_MISSING
  DIGEST_MISMATCH
  SNAPSHOT_REVOKED
  RESTORE_FAILED
SECURITY
  NAMESPACE_MISMATCH
  AUTHORIZATION_DENIED
ECONOMIC_BYPASS
  RESTORE_MORE_EXPENSIVE_THAN_RECOMPUTE
UNSUPPORTED
UNKNOWN
```

`UNKNOWN` consumes the unexpected-miss error budget.

## 14. Benchmark corpus

Mandatory scenarios:

1. `EXACT_RERUN`
2. `STABLE_10_TURN`
3. `EDIT_LE_1_PERCENT`
4. `IMPLEMENTATION_ONLY`
5. `FORMATTING_ONLY`
6. `PUBLIC_INTERFACE_CHANGE`
7. `LOCKFILE_CHANGE`
8. `RULE_PACK_CHANGE`
9. `MODEL_SWITCH`
10. `EFFORT_SWITCH`
11. `TOOL_SCHEMA_CHANGE`
12. `ENVIRONMENT_WARM`
13. `SERVICE_RESTART`
14. `WORKER_FAILOVER`
15. `PROVIDER_TTL_EXPIRY`
16. `LONG_SESSION_100_TURN`
17. `CONTEXT_COMPACTION_ROLLBACK`
18. `CACHE_STORE_OUTAGE`
19. `CORRUPT_OBJECT_NEGATIVE`
20. `CROSS_TENANT_NEGATIVE`

Corpus dimensions include repository size, language/framework, source-to-target conversion, project generation, model provider, effort profile, operating platform, and network regime. Tuning and final certification windows are separated.

## 15. Rollout

```text
observe only
  -> shadow / counterfactual
  -> internal/dogfood
  -> canary tenants
  -> 5%
  -> 25%
  -> 50%
  -> 100%
```

Immediate rollback triggers:

- any accepted false hit, cross-tenant hit, corrupt execution, or under-validated publication;
- mandatory SLO/error-budget breach;
- unknown outcome rate above budget;
- provider usage/accounting mismatch;
- fairness or worst-cohort regression;
- cache decision overhead, network, storage, or provider write cost above guardrail;
- OOD/drift with no valid certificate;
- inability to execute the certified no-cache/clean-rebuild fallback.

## 16. Required implementation modules

- provider prompt-cache adapter registry;
- canonical Prompt IR/compiler/manifests/linter;
- append-only context ledger and projector;
- context checkpoint/compaction planner;
- environment snapshot builder/restorer/revoker;
- cache affinity inventory and scheduler;
- multi-layer reuse coordinator and singleflight;
- miss diagnostics and first-difference explainers;
- parity scenario runner/report/certificate;
- SLO autotuner, shadow/canary controller, and rollback;
- dashboards, runbooks, migrations, security and chaos tests.

## 17. Security and correctness

- cache namespaces isolate tenants, projects, trust domains, providers, models, and compatibility groups;
- telemetry uses opaque digests and never raw prompts/source/secrets as labels;
- source and artifacts remain protected by authorization independent of cache identity;
- provider prompt caches cannot be used as persistent memory or evidence;
- semantic/learned caches produce candidates only;
- all generated files follow `RESERVED -> WRITING -> SEALED -> CAS_PROMOTED -> TREE_INCLUDED -> PUBLISHED`;
- publication requires declared validation level and complete-tree atomicity;
- false hit count is a security/correctness metric, not an availability tradeoff.

## 18. Completion rule

The package defines the work and supplies reference components. The actual ELMOS subsystem reaches parity only when the production repository implements the Skills and a fresh signed report passes all mandatory gates. Package validation alone proves package integrity, not production cache performance.
