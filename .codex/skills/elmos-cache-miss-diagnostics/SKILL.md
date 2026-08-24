---
name: elmos-cache-miss-diagnostics
description: Assign every cache miss, bypass, eviction, failed restore, and invalidation a precise machine-readable reason with causal lineage and remediation guidance.
version: 1.2.0
package: elmos-build-cache-staging-codex-claude-parity
phase: P11-parity-control-plane
dependencies: [elmos-multi-layer-cache-coordinator, elmos-cache-observability-performance, elmos-cache-key-fingerprinting]
---

# Cache Miss Diagnostics and Invalidation Explainability

## Outcome

Make low cache reuse diagnosable by stage, provider, prompt segment, environment dimension, shard, tenant, and invalidation edge instead of relying on aggregate hit rate. This is an implementation skill. The coding agent must modify the actual ELMOS repository, run reproducible verification, and attach evidence; prose, simulated counters, or a disconnected prototype are not completion.

## Use this skill when

- A parity SLO fails or a cache regression occurs after prompt/tool/model/repository/environment changes.
- Operators need to answer why an expected hit became a miss and whether the miss was necessary.
- Building automated remediation and rollout rollback rules.

## Required inputs

- All lookup/plan observations, ActionKey explanations, Prompt Prefix Manifests, provider usage, environment snapshot keys, worker placement decisions, DAG invalidation graph, cache events, and retention/eviction history.
- Miss taxonomy and privacy-safe diagnostic policy.
- Expected-hit annotations from benchmark scenarios.

## Produced artifacts

- Canonical hierarchical `CacheOutcomeReason` taxonomy and versioned event schema.
- First-difference engines for prompt prefix, ActionKey, repository snapshot/public interface, environment snapshot, and provider namespace.
- Causal miss graph from user edit/config change through invalidated nodes and realized recomputation.
- `elmos cache explain` CLI/API, dashboard funnels, regression detector, and remediation hints.
- Miss-budget reports by stage/cohort and automated SLO rollback triggers.

## Non-negotiable invariants

- Every request/layer produces exactly one terminal outcome: hit, necessary miss, unexpected miss, bypass, restore failure, or lookup error.
- Reason codes are derived from recorded evidence, never guessed from latency.
- Diagnostics redact source, prompts, secrets, and sensitive tenant identifiers while retaining stable opaque digests.
- Necessary invalidation and avoidable cache-system failure are reported separately.
- Unknown outcomes are explicit `UNKNOWN_*` failures that consume the unexpected-miss budget.
- Changing the taxonomy is versioned and backward-compatible in analytics.

## Execution workflow

1. Instrument terminal outcomes for every cache layer and coordinator plan.
2. Implement first-difference comparison for all canonical key/manifest types.
3. Link misses to upstream change events, invalidation edges, policy eviction, TTL, routing, corruption, or restore-cost bypass.
4. Build explain CLI/API and aggregate funnels from eligible requests to realized end-to-end savings.
5. Run fault injection and golden miss scenarios to guarantee unique correct classification.
6. Feed unexpected-miss cohorts to autotuning/rollout gates and verify automated rollback.

## Implementation tasks

1. Define top-level families `COLD`, `IDENTITY_CHANGED`, `TTL_OR_RETENTION`, `PLACEMENT`, `CAPACITY_POLICY`, `RESTORE`, `SECURITY`, `CORRUPTION`, `ECONOMIC_BYPASS`, `UNSUPPORTED`, and `UNKNOWN`.
2. Include leaf reasons such as `MODEL_CHANGED`, `EFFORT_CHANGED`, `TOOL_SCHEMA_CHANGED`, `PROMPT_SEGMENT_CHANGED`, `PUBLIC_INTERFACE_CHANGED`, `RULE_PACK_CHANGED`, `LOCKFILE_CHANGED`, `ENVIRONMENT_CHANGED`, `TTL_EXPIRED`, `CACHE_EVICTED`, `WRONG_SHARD`, `SNAPSHOT_REVOKED`, and `RESTORE_MORE_EXPENSIVE_THAN_RECOMPUTE`.
3. Build segment/dimension diff output with old/new digests, compatibility versions, source change event, affected DAG nodes, and recomputation cost.
4. Separate eligibility denominator from all requests so cold starts or intentionally uncacheable work cannot inflate/deflate parity metrics.
5. Add expected-hit markers to benchmark traces and flag a miss as unexpected when no legitimate invalidator exists.
6. Create top-loss ranking by avoidable model tokens, compute milliseconds, critical-path milliseconds, bytes, and monetary cost.
7. Emit targeted remediation hints, such as canonicalize tools, stabilize prefix, increase affinity, extend retention, fix over-invalidation, or reduce restore cost.
8. Implement sampling that retains all errors/SLO violations while controlling successful high-volume events.

## Acceptance criteria

- 100% of golden miss scenarios map to the expected unique leaf reason and causal source.
- At least 99.9% of production-eligible observations receive a non-unknown outcome; unknowns trigger an alert and consume SLO budget.
- First-difference diagnostics identify the exact prompt segment, ActionKey dimension, environment input, or DAG edge for deterministic fixtures.
- No raw prompt/source/secret appears in diagnostic labels, exported traces, or dashboards.
- The parity benchmark can fail on an unexpected miss and prints a human-actionable explanation.
- Reason totals reconcile with layer request totals and unified reuse attribution.

## Evidence required

- Taxonomy/schema, golden scenario suite, first-difference implementation, and sample explain outputs.
- Privacy/redaction test report and cardinality review.
- Reconciliation dashboard, top-loss report, and an injected regression that triggers rollback.
- Known unknown/unsupported cases and explicit handling plan.

## Anti-patterns

- Using only `HIT` and `MISS` labels.
- Inferring cache hits from low latency or misses from high latency.
- Mixing cold starts, necessary invalidations, evictions, wrong-shard misses, and corruption in one denominator.
- Logging entire prompts or source diffs to make diagnosis easier.
- Treating `UNKNOWN` as successful telemetry.

## Done condition

The skill is done when every layer has terminal outcomes, exact first-difference diagnostics, causal miss graphs, privacy-safe explain tooling, reconciled funnels, golden tests, and unexpected misses can block or roll back a release.
