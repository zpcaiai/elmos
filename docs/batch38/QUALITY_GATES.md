# Batch 38 quality gates

Certification requires nonempty evidence, complete holdout and representative passes, zero critical findings, all evidence claims passing, and these metrics:

- `editionConformanceRate` must satisfy `min 1.0`.
- `upgradeRollbackPassRate` must satisfy `min 1.0`.
- `recoveryPassRate` must satisfy `min 1.0`.

Status-only certification and unauthorized external evidence must be rejected.
