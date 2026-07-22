---
name: quality-gate-release-confidence-and-risk-decision-engine
description: Aggregate fresh test, risk, contract, mutation, flaky, data, model, environment, journey, nonfunctional, and security evidence into independent quality gates and release confidence. Use for merge, release, conditional-pass, or risk decisions.
---

# Quality Gate and Release Confidence

## Evaluate all dimensions

Evaluate build, discovery, unit, component, contract, integration, E2E, property, mutation, flaky, data, model, visual, accessibility, performance, security, and resilience evidence. Keep hard and soft gates separate and scope thresholds by versioned risk/domain rather than one global average.

## Enforce hard failures

Fail on new critical test failure, breaking contract, uncovered critical risk, anomalous test-count drop, critical data inconsistency, critical security finding, flaky critical journey, or evidence bound to an old commit/artifact. Treat not-run, unknown, missing, stale, and insufficient environment fidelity as non-pass states.

## Explain confidence

Report evidence coverage/freshness, risk coverage, test effectiveness, environment fidelity, flaky reliability, and unknown areas. Classify confidence as high, moderate, low, insufficient, or unknown; do not average away a critical blocker.

## Constrain exceptions

For a conditional pass, require condition, owner, due date, monitoring, expiry, and revalidation. Invalidate it at expiry. Keep risk acceptance and gate override with qualified human authority.

## Detect metric gaming

Reject deleted tests, coverage exclusions, removed mutants, auto-approved snapshots, ignored flaky tests, widened tolerances, or reused old evidence intended to improve metrics. Bind the decision to the current artifact and evidence-manifest hash.
