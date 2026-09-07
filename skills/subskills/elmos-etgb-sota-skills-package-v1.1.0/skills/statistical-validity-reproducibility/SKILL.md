---
name: statistical-validity-reproducibility
description: Make probabilistic ETGB evaluations reproducible and statistically honest with fixed seeds, confidence intervals, stability analysis and non-inferiority decisions.
---

# Statistical Validity and Reproducibility

## Deterministic envelope

Pin candidate, case, corpus, Environment, image, dependency lock, Oracle, normalization, locale, timezone, clock policy and random seeds. Record nondeterministic APIs and scheduler assumptions.

## Multi-seed policy

Probabilistic generation/translation uses at least three declared fixed seeds for PR/nightly evidence and more for release comparisons when variance is material. Execute every declared seed and report pass distribution, repair turns, usage, machine wall-clock and worst case.

## Confidence

Use Wilson intervals for binomial pass rates. Compare candidates to a baseline through a predeclared non-inferiority margin rather than raw point estimates alone. Report sample size and inconclusive outcomes; do not label an underpowered comparison as improvement.

## Stability

For each case, compare statuses, semantic results, failure class, artifact digest where determinism is expected, duration coefficient of variation and cost variance. Investigate divergence before aggregating.

## Multiple comparisons

When ranking many models, language pairs or stacks, predeclare primary metrics and control false discoveries or treat secondary comparisons as exploratory. Never repeatedly tune against hidden release tests.

## Missing data

Skipped, unavailable, timed-out and source-broken cases remain explicit. Do not silently delete them. Release metrics that lack required samples are `BLOCKED`, not zero or pass.

## Reproduction bundle

Include commands, exact seeds, candidate/plan digests, Environment policy, dependency/image digests and evidence. A reproduced run should independently verify the same semantic decision even when performance varies within tolerance.

## Implementation

Use `etgb/statistics.py` and `etgb stability`. Statistical policy/version is part of the release candidate and evidence.
