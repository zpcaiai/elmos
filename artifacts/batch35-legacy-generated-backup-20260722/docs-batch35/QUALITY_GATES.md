# Batch 35 quality gates

Certification requires nonempty evidence, complete holdout and representative passes, zero critical findings, all evidence claims passing, and these metrics:

- `oracleCoverageRate` must satisfy `min 0.95`.
- `counterexampleReplayRate` must satisfy `min 1.0`.
- `criticalInvariantPassRate` must satisfy `min 1.0`.

Status-only certification and unauthorized external evidence must be rejected.
