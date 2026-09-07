---
name: elmos-cache-hit-slo-autotuning
description: Continuously tune cache layout, admission, capacity, retention, routing, prefetch, compaction, and environment policy against parity SLOs with safe shadowing, canaries, drift detection, and automatic rollback.
version: 1.2.0
package: elmos-build-cache-staging-codex-claude-parity
phase: P12-parity-certification
dependencies: [elmos-codex-claude-parity-benchmark, elmos-learning-augmented-cache-control, elmos-adaptive-cache-policy-orchestrator]
---

# Cache Hit SLO Autotuning and Regression Control

## Outcome

Turn parity thresholds into continuous operational controls that improve real avoided work while preventing learned or heuristic policies from entering the correctness path. This is an implementation skill. The coding agent must modify the actual ELMOS repository, run reproducible verification, and attach evidence; prose, simulated counters, or a disconnected prototype are not completion.

## Use this skill when

- Production workload differs from the benchmark corpus or hit rates drift over time.
- Tuning cache capacities, provider TTL modes, prompt layout variants, affinity weights, prefetch, retention, or compaction thresholds.
- A release needs automatic rollback when cache value or correctness regresses.

## Required inputs

- Parity report and live privacy-reviewed traces, SLO policy, cost models, capacity/budget limits, cohort definitions, current/baseline policies, drift/OOD features, and rollback controls.
- Provider quotas/TTL economics, worker/storage/network limits, and tenant fairness policy.
- All miss diagnostic reason codes and unified reuse attribution.

## Produced artifacts

- Versioned `CacheSLOPolicy` with eligibility, targets, error budgets, worst-cohort floors, and correctness gates.
- Offline optimizer/replay pipeline, shadow counterfactual evaluator, bounded parameter controller, and policy certificate lifecycle.
- Canary/progressive rollout controller with auto rollback and frozen safe baseline.
- Drift/OOD detector and retraining/retuning trigger.
- SLO dashboards and weekly regression report.

## Non-negotiable invariants

- No autotuner may change ActionKey semantics, digest verification, tenancy, authorization, validation level, staged-file state machine, or publication correctness.
- Optimization targets net avoided work/cost/critical path under correctness and fairness constraints, not raw hit rate alone.
- The final certification corpus is never used for tuning.
- All changes are bounded, versioned, reversible, and evaluated in shadow before write influence.
- Low confidence, OOD, missing telemetry, excessive overhead, or SLO regression immediately falls back to a fixed certified policy/configuration.
- No tenant can buy higher cache reuse by causing starvation, cross-tenant leakage, or uncontrolled storage/network cost.

## Execution workflow

1. Translate parity targets into per-layer and end-to-end SLOs with eligibility and error-budget rules.
2. Replay candidate configurations on time-separated traces and reject those that fail correctness, worst-cohort, capacity, overhead, or fairness constraints.
3. Run shadow/counterfactual evaluation using live decisions without changing production behavior.
4. Canary a bounded cohort and compare against a simultaneous control using sequential/regression-safe statistics.
5. Progressively roll out only while all SLOs and leading indicators pass; roll back automatically on breach.
6. Detect workload drift/OOD, expire certificates, and repeat tuning using fresh traces.

## Implementation tasks

1. Define primary SLOs for stable-prefix reuse, unexpected prefix miss, exact rerun reuse, small-edit reuse, unnecessary invalidation, environment hit/warm-start, restart reuse, wall-clock/token savings, and zero false hits.
2. Set error budgets and minimum sample sizes per provider/model/language/framework/repository-size/tenant cohort, including a worst-cohort floor.
3. Search bounded parameters for prefix breakpoint placement, provider TTL class, cache capacities, admission/eviction policy, retention, affinity weights, prefetch horizon, restore threshold, and compaction timing.
4. Use multi-objective Pareto selection and require a configurable margin over baseline after accounting for decision overhead and confidence intervals.
5. Implement immutable policy/config snapshots, signed certificates, expiry/revocation, and one-command rollback to the last certified baseline.
6. Add change attribution linking each SLO movement to prompt segment, miss reason, capacity/eviction, routing, environment, or workload drift.
7. Protect provider spending with cache-write/read break-even and quota budgets; disable expensive long-lived writes when expected reads do not justify them.
8. Run periodic chaos controls to ensure fallbacks, no-cache mode, and rebuild paths remain healthy.

## Acceptance criteria

- Autotuning never modifies correctness-path identities or permissions; policy diff enforcement rejects such changes.
- Every production-influencing configuration has passed replay, shadow, canary, and certificate gates and has a tested rollback.
- A simulated 5% degradation in any mandatory parity SLO or any false hit triggers automatic halt/rollback within the configured detection window.
- The tuner improves or preserves net wall-clock/cost and worst-cohort outcomes versus the certified baseline; raw hit gains with negative net value are rejected.
- Drift/OOD and telemetry-loss tests select the fixed safe baseline and emit actionable incidents.
- Provider cache-write spending remains within configured break-even/error budget.

## Evidence required

- SLO policy/config schema, optimizer source, candidate Pareto reports, shadow/canary/control statistics, and policy certificates.
- Automatic rollback and safe-baseline exercises, including false-hit and telemetry-loss injection.
- Per-cohort dashboards, change attribution, drift/OOD reports, and provider cache economics.
- Audit trail for every production policy/config transition.

## Anti-patterns

- Allowing a learned model to decide whether two ActionKeys are equivalent.
- Tuning against the final test set or only global averages.
- Switching policies per request and causing oscillation/state loss.
- Keeping a higher hit-rate configuration that increases total latency, token cost, network bytes, or tenant unfairness.
- Continuing adaptive decisions when telemetry, model, or state is unavailable.

## Done condition

The skill is complete when parity SLOs, error budgets, offline/shadow/canary tuning, certificate lifecycle, drift/OOD fallback, provider economics, automatic rollback, and regression evidence operate continuously with a frozen safe baseline.
