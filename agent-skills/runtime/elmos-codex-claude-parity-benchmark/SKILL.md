---
name: elmos-codex-claude-parity-benchmark
description: Benchmark ELMOS cache behavior using reproducible coding-agent workloads and hard gates for prompt-token reuse, exact work reuse, incremental invalidation, environment warm starts, recovery, latency, cost, and zero false hits.
version: 1.2.0
package: elmos-build-cache-staging-codex-claude-parity
phase: P12-parity-certification
dependencies: [elmos-cache-miss-diagnostics, elmos-cache-trace-replay-simulator, elmos-cache-chaos-certification, elmos-cache-autotuning-certification]
---

# Codex/Claude-Class Cache Parity Benchmark

## Outcome

Provide a defensible, provider-normalized certification that ELMOS reaches or approaches Codex/Claude-class cache behavior on explicitly defined warm workloads, without claiming an unpublished vendor-wide hit percentage. This is an implementation skill. The coding agent must modify the actual ELMOS repository, run reproducible verification, and attach evidence; prose, simulated counters, or a disconnected prototype are not completion.

## Use this skill when

- Preparing a release that claims high coding-agent cache reuse or comparing ELMOS with Codex/Claude Code behavior.
- Changing prompt layout, provider adapter, context ledger, environment snapshots, routing, invalidation, or cache policy.
- Investigating whether high raw hit rate produces real end-to-end savings.

## Required inputs

- Pinned ELMOS commit/config, provider/model/effort/tool profiles, benchmark repositories, edit scripts, expected DAG invalidation, environment fixtures, long-session scripts, failure scenarios, and cost/latency normalization.
- Cold and warm control runs with cache layers selectively disabled.
- Miss diagnostics, provider usage observations, Action Cache/CAS data, and hardware/network profile.

## Produced artifacts

- Versioned parity corpus and scenario runner with deterministic edit/task scripts.
- Machine-readable `CacheParityReport`, per-scenario evidence bundle, confidence intervals, and regression baseline.
- Cold/warm/provider-only/action-only/full-stack ablation results.
- Pass/fail certificate bound to code, configuration, provider profiles, corpus, platform, and date.
- Public-claim wording guard that distinguishes package targets from measured production results.

## Non-negotiable invariants

- The benchmark never invents or attributes a single undocumented universal hit rate to Codex or Claude Code.
- Parity is evaluated on defined workloads and normalized mechanisms: stable-prefix token reuse, exact Action reuse, incremental compute reuse, environment warm start, recovery, latency, cost, and correctness.
- Train/tuning traces are separated from final certification scenarios; equal-capacity and equal-task comparisons are enforced.
- Cold starts, deliberately uncacheable work, and necessary invalidations are visible but do not masquerade as unexpected misses.
- All results include zero-false-hit, tenant isolation, corruption, and validation-level gates; performance cannot compensate for correctness failure.
- Provider/network variability is controlled with repetitions, confidence intervals, and recorded profile metadata.

## Execution workflow

1. Materialize the corpus with small, medium, and large repositories across supported languages/frameworks and generate deterministic initial/follow-up/edit/retry/restart scripts.
2. Run cold controls and layer ablations, then warm conversations and exact reruns with pinned provider/model/effort/tool profiles.
3. Execute edit classes: formatting-only, implementation-only, public-interface, dependency/lockfile, rule-pack, tool-schema, model/effort, and large refactor.
4. Run environment cold/warm, service restart, worker failover, provider TTL expiry, context compaction, and cross-tenant isolation scenarios.
5. Collect provider token usage, Action reuse, invalidation closure, environment restore, latency/cost, miss reasons, and correctness evidence.
6. Calculate gates, worst-cohort results, uncertainty, and issue a signed report/certificate only if every mandatory gate passes.

## Implementation tasks

1. Define scenarios `EXACT_RERUN`, `STABLE_10_TURN`, `EDIT_LE_1_PERCENT`, `IMPLEMENTATION_ONLY`, `PUBLIC_INTERFACE_CHANGE`, `ENVIRONMENT_WARM`, `SERVICE_RESTART`, `WORKER_FAILOVER`, `LONG_SESSION_100_TURN`, `MODEL_SWITCH`, `TOOL_SCHEMA_CHANGE`, and `CROSS_TENANT_NEGATIVE`.
2. Require stable-conversation eligible cached-token reuse >=90% after turn 3 and unexpected full-prefix miss rate <=2%.
3. Require exact rerun compute-weighted Action reuse >=99% with zero redundant model/compiler/test calls for already validated actions.
4. Require <=1% edits with unchanged public interfaces to achieve compute-weighted reuse >=90%; implementation-only unnecessary downstream invalidation <=5%.
5. Require unchanged environment snapshot hit >=95% and p95 warm-start >=80% faster than cold controls.
6. Require restart sealed-artifact reuse >=99.9%; stable same-project follow-ups net wall-clock saved >=70% and model input cost saved >=80%.
7. Require long-session completion without context overflow and >=80% eligible cached-token reuse after planned compaction warmup.
8. Require accepted false hits, cross-tenant hits, corrupt-object executions, and under-validated releases all equal zero.
9. Report raw object/byte hit ratios only as secondary metrics beside avoided compute, tokens, critical path, wall-clock, monetary savings, and quality/build/test outcomes.
10. Bind certificates to source/config/corpus/provider/platform digests and expire them after material change or workload drift.

## Acceptance criteria

- All mandatory thresholds above pass on the final untouched corpus and no worst supported language/framework cohort falls below its configured floor.
- Results are reproducible within declared tolerance across at least three repetitions or explain provider variance with confidence intervals.
- A deliberately broken prompt layout, over-invalidation rule, wrong-shard router, and corrupt cache object each cause the expected benchmark failure.
- A report clearly distinguishes measured ELMOS results from target thresholds and from official provider mechanism descriptions.
- Every scenario includes exact commands, environment/profile metadata, miss-reason distribution, and correctness evidence.
- No certification is issued from synthetic traces alone when production parity is claimed.

## Evidence required

- Corpus manifest and licenses/synthetic provenance, scenario scripts, source/config/provider/platform digests, and raw event bundle.
- Cold/warm/ablation tables, confidence intervals, per-cohort gates, miss reasons, and top avoided-work losses.
- Build/test/behavior validation and security/chaos results, including zero-false-hit proof.
- Signed machine-readable report/certificate and failed-certificate example.

## Anti-patterns

- Quoting a vendor-wide cache hit rate that is not publicly defined.
- Benchmarking only exact reruns or only one tiny repository.
- Optimizing a synthetic trace used for final testing.
- Reporting object hit rate while omitting token, compute, latency, cost, and correctness.
- Excluding failed, slow, cold, or wrong-shard runs from the denominator without a declared eligibility rule.

## Done condition

Completion requires a runnable parity corpus, pinned and repeatable scenario runner, ablations, hard SLO gates, zero-false-hit certification, failure injections, signed report, and honest claim wording integrated into CI/release review.
