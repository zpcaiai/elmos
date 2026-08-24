---
name: elmos-cache-affinity-routing
description: Route sessions and DAG nodes to provider cache shards, model replicas, workers, environment snapshots, and local CAS holdings that maximize verified reusable work without sacrificing fairness or availability.
version: 1.2.0
package: elmos-build-cache-staging-codex-claude-parity
phase: P10-environment-affinity
dependencies: [elmos-provider-prompt-cache-adapters, elmos-environment-snapshot-cache, elmos-dag-aware-cache-prefetch, elmos-remote-shared-cache]
---

# Cache Affinity Routing

## Outcome

Turn existing cache state into actual hits by co-locating follow-up work with the compatible provider prefix, model replica, environment, and artifacts. This is an implementation skill. The coding agent must inspect and modify the actual ELMOS repository, run reproducible verification, and attach evidence. A design document, mocked counter, or isolated demo is not completion.

## Use this skill when

- Cache entries exist but requests land on cold workers/replicas or wrong provider shards.
- ELMOS schedules multi-tenant, multi-model, multi-stage conversion DAGs across a worker fleet.
- Warm environment and local CAS reuse must be balanced against queue latency, reliability, and fairness.

## Required inputs

- Prompt cache namespace/affinity key, provider routing capabilities, model/effort/tool profile, project/branch/session identity, DAG next-use, worker inventory, local CAS bloom/summary, environment snapshots, queue/load, quotas, and health.
- Affinity decision schema, privacy policy, and scheduler interfaces.
- Historical hit/miss and queue/service-time traces.

## Produced artifacts

- `CacheAffinityKey`, worker/replica cache inventory protocol, placement scorer, bounded-staleness index, and routing decision record.
- Multi-objective scheduler integration with hard compatibility filters and soft locality scoring.
- Consistent/rendezvous hashing option for stable provider/model routing plus overload-aware escape.
- Fairness, failover, rebalance, and cache-warm migration controls.
- Scheduler replay and production metrics.

## Non-negotiable invariants

- Compatibility, authorization, health, capacity, and required runtime constraints are hard filters before cache locality is considered.
- Affinity is a preference, not a reason to route to an unhealthy, unauthorized, overloaded, or incompatible worker.
- Routing keys contain opaque digests and never expose source, prompt, secret, or tenant content to other workers.
- Provider/model/effort/tool/prefix compatibility is exact; local CAS and environment claims are verified on use.
- Tenant fairness and starvation limits remain enforceable under hot-project concentration.
- Failover may lose a cache hit but must not lose durable task state or produce duplicate side effects.

## Execution workflow

1. Instrument current scheduler decisions and quantify wrong-shard, wrong-replica, cold-worker, and queue-delay misses.
2. Define hard compatibility filters and a locality benefit estimate net of queueing, transfer, restore, and recompute costs.
3. Implement worker inventory summaries and bounded-staleness propagation.
4. Add stable hashing for provider/model prefixes and weighted scoring for environment/local CAS/DAG artifacts.
5. Replay traces with failures and skew; then shadow decisions before enabling placement influence.
6. Canary with overload escape, fairness guards, automatic rollback, and no durable-state coupling to one worker.

## Implementation tasks

1. Construct `CacheAffinityKey = H(tenant-scope, project, branch, provider, model, effort, tool-profile, stable-prefix-compatibility)` with configurable privacy-preserving scopes.
2. Publish worker capabilities, model replicas, environment snapshot IDs, local artifact summaries, queue estimates, and freshness epochs.
3. Implement score components for expected prompt-cache value, environment restore savings, local CAS bytes/recompute savings, DAG next-use, queue delay, transfer cost, reliability, and fairness debt.
4. Use rendezvous/consistent hashing for stable shards while allowing bounded-load redirection and secondary choices.
5. Add singleflight and lease coordination so simultaneous identical misses do not stampede one worker/provider.
6. Record selected and counterfactual candidates with reason codes such as `PREFIX_LOCAL`, `ENV_LOCAL`, `ARTIFACT_LOCAL`, `OVERLOAD_ESCAPE`, and `FAIRNESS_OVERRIDE`.
7. Add failure tests for worker death, stale inventory, network partition, provider replica churn, hot tenant, and rebalance.
8. Expose wrong-shard rate, locality hit conversion, queue penalty, failover cost, and per-tenant fairness.

## Acceptance criteria

- Wrong-shard/replica misses are at most 1% in stable-provider benchmark scenarios where routing control is available.
- Affinity routing improves net avoided work and does not worsen p95 end-to-end latency or worst-tenant service by more than configured guardrails.
- Worker failure reroutes safely without duplicate publication or loss of checkpointed work.
- Stale inventory produces a verified normal miss, never a false hit.
- Hot-project stress tests satisfy fairness, bounded-load, and starvation SLOs.
- Every placement decision is explainable from recorded compatible candidates and score components.

## Evidence required

- Scheduler integration, affinity key schema, inventory protocol, scoring configuration, and decision examples.
- Replay/shadow/canary comparison of wrong-shard rate, hit conversion, queue latency, transfer, and fairness.
- Failure, overload, stale-inventory, singleflight, and cross-tenant tests.
- Rollback trace proving locality can be disabled without stopping task execution.

## Anti-patterns

- Pinning a session forever to one worker regardless of health or queue.
- Routing by raw tenant/project/prompt strings or exposing cache inventory across tenants.
- Believing a worker inventory claim without digest verification.
- Optimizing locality while hiding queue-delay or fairness regressions.
- Coupling durable task ownership to an ephemeral cache shard.

## Done condition

The skill is complete when compatibility-safe affinity routing, inventory, locality scoring, overload/fairness escape, singleflight, replay/canary evidence, failure recovery, and explainable metrics are operating in the actual ELMOS scheduler.
