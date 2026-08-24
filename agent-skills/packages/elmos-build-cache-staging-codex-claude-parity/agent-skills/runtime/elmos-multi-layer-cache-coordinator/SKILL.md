---
name: elmos-multi-layer-cache-coordinator
description: Coordinate provider prompt caches, exact Action Cache, CAS, repository context, environment snapshots, native build caches, and staged artifacts as one correctness-preserving lookup and execution plan.
version: 1.2.0
package: elmos-build-cache-staging-codex-claude-parity
phase: P11-parity-control-plane
dependencies: [elmos-cache-affinity-routing, elmos-cache-preserving-context-compaction, elmos-action-cache, elmos-checkpoint-resume, elmos-cost-aware-cache-admission]
---

# Multi-Layer Cache Coordinator

## Outcome

Make every request choose the highest-value verified reuse path and prevent duplicate work or double-counted savings across cache layers. This is an implementation skill. The coding agent must modify the actual ELMOS repository, run reproducible verification, and attach evidence; prose, simulated counters, or a disconnected prototype are not completion.

## Use this skill when

- A task can reuse prompt prefixes, deterministic stage results, local/remote artifacts, environment snapshots, native build outputs, or checkpoints.
- The system reports high individual-layer hit rates but weak end-to-end latency/cost savings.
- Implementing a singleflight, restore-versus-recompute, or partial-hit execution plan.

## Required inputs

- All cache-layer interfaces, trust/validation levels, provider observations, DAG, stage contracts, artifact manifests, environment snapshots, context ledger, worker locality, and cost models.
- Request classification and required output validation level.
- Layer-specific timeout, quota, bypass, fallback, and telemetry configuration.

## Produced artifacts

- `CacheReusePlan` with ordered probes, parallel-safe probes, validation requirements, estimated value, and fallback path.
- Unified singleflight/deduplication coordinator for exact work identities.
- Partial-hit planner that reconstructs the remaining DAG from verified stage boundaries.
- Unified accounting ledger that attributes avoided work to exactly one primary layer and records supporting layers.
- Cross-layer chaos and performance tests.

## Non-negotiable invariants

- Exact Action Cache/verified artifact reuse takes precedence over a model call when the requested ActionKey and validation level match.
- Provider prompt cache can reduce model input processing but does not make the model output deterministic or validated.
- No layer may downgrade the required validation, tenancy, provenance, freshness, or publication guarantees.
- A reported end-to-end hit means requested work was actually avoided; metadata lookup, failed restore, or speculative prefetch alone is not a hit.
- Savings are not double counted when an environment, prompt prefix, and Action Result all participate in one request.
- Singleflight coalesces only identical authorized work and preserves independent cancellation, deadlines, and result delivery.

## Execution workflow

1. Map each ELMOS request class to legal reuse layers and required validation levels.
2. Build a deterministic reuse planner that checks checkpoint, exact Action Cache, local/remote CAS, environment, provider prefix, and recompute options using bounded parallelism.
3. Integrate singleflight and negative-cache/backoff for repeated deterministic failures without hiding recoverable changes.
4. Implement partial-hit DAG reconstruction and stage-level provenance propagation.
5. Unify accounting and compare planned versus realized cost/latency.
6. Exercise layer outages, corruption, stale entries, false inventory claims, provider no-cache, and concurrent identical requests.

## Implementation tasks

1. Define cache-layer capabilities: identity type, exactness, trust level, lookup/restore cost, validation, TTL, locality, and failure semantics.
2. Implement `CacheReusePlan` decisions `REUSE_EXACT_RESULT`, `RESTORE_ARTIFACTS`, `RESUME_CHECKPOINT`, `WARM_ENVIRONMENT`, `USE_PROMPT_PREFIX`, `EXECUTE_REMAINDER`, and `FULL_RECOMPUTE`.
3. Run independent safe lookups concurrently but serialize promotion/publication and protect storage from stampedes.
4. Implement restore-versus-recompute based on predicted net wall-clock, monetary cost, critical-path impact, and confidence, with deterministic fallback.
5. Propagate validation evidence and require revalidation when cached evidence is below the requested level or invalidated by changed dependencies.
6. Add a unified `ReuseAttribution` record with one primary avoided action and optional enabling-layer contributions.
7. Support partial results such as cached AST/IR with regenerated code/test stages and explain exactly which invalidation edge caused each miss.
8. Add budgets for lookup fan-out, remote bytes, prefetch, provider cache writes, environment restores, and coordinator decision latency.

## Acceptance criteria

- Exact identical reruns achieve at least 99% compute-weighted Action Cache reuse and issue zero redundant model/compiler/test calls for already validated actions.
- Small-edit parity scenarios execute only the invalidated DAG closure and meet the 90% compute-weighted reuse gate when public interfaces are unchanged.
- Coordinator p95 overhead stays below 10 ms locally and the configured distributed budget, excluding external restores.
- Unified accounting reconciles within 0.5% of raw provider, worker, and storage counters and never double counts avoided work.
- Every false, corrupt, stale, cross-tenant, or under-validated candidate becomes a safe miss; accepted false hits equal zero.
- Outage of any optional cache layer degrades to a correct slower path without losing staged files or checkpoints.

## Evidence required

- Reuse-plan source, layer capability registry, partial-hit DAG traces, and exact-result/no-model-call tests.
- Concurrency/singleflight, corruption, timeout, outage, and validation-level test results.
- Accounting reconciliation and per-layer/end-to-end savings report.
- Representative explain output for full hit, partial hit, prompt-only hit, environment-only hit, and full miss.

## Anti-patterns

- Checking every cache serially with unbounded latency.
- Calling a provider prompt-cache read an exact model-output hit.
- Returning cached generated code whose validation level or dependencies do not match the request.
- Counting the same saved model call under prompt, Action, and environment caches.
- Starting duplicate executions before singleflight identity and authorization are resolved.

## Done condition

Completion requires the production reuse planner, singleflight, partial-DAG execution, validation/provenance propagation, unified attribution, fallback behavior, and parity/chaos tests to pass with zero false hits.
