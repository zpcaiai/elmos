# ADR-0043: Independent test and quality engineering engine

## Status

Accepted for Batch 18 repository scope on 2026-07-21.

## Context

ELMOS already had language/domain engines and an independent migration judge, but individual green test reports could not prove discovery completeness, business-risk coverage, assertion strength, mutation effectiveness, environment fidelity, or flaky reliability. The test executor must not also decide whether its own output authorizes a release.

## Decision

Add `ELMOS_TEST_QUALITY` as an eighth independent Java 21 execution domain. Route tool/framework behavior through versioned adapters and six isolated runner types. Keep all runners rootless, digest-pinned, ephemeral, default-deny, tenant/run namespaced, resource-bounded, cancellable, and dependent on short-lived environment and test-data leases.

Use stable cross-run Test Identity and reconcile source, discovered, executed, and reported counts. Model quality risk independently from line coverage. Require reviewed characterization/golden artifacts, explicit consumer/provider compatibility, replayable properties and minimal examples, separate mutation metrics, visible flaky attempts, conservative impact selection, and current-artifact evidence.

Keep the quality-gate policy independent from workers. AI output remains a candidate until compile/run, fail-before-fix, repeatability, isolation, mutation, and human review succeed. Unknown, stale, skipped, missing, and not-run evidence never becomes pass.

Reuse shared tenant, workflow, risk, approval, evidence, audit, billing, delivery, and the V7 `test_suites`/`test_case_identities` authorities. V18 adds quality projections with forced RLS and append-only evidence records.

## Consequences

Repository tests can prove deterministic policy, contracts, fixtures, persistence boundaries, and fail-closed adapters. They cannot prove customer tests, devices, browsers, performance environments, data sets, external test-management systems, or production validation ran. Those remain `NOT_CONFIGURED`, `NOT_RUN`, `INCONCLUSIVE`, or `BLOCKED` until independently evidenced.
