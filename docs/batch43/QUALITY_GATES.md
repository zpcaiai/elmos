# Batch 43 quality gates

Certification requires nonempty evidence, complete holdout and representative passes, zero critical findings, all evidence claims passing, and these metrics:

- `compatibilityMatrixPassRate` must satisfy `min 1.0`.
- `upgradePassRate` must satisfy `min 1.0`.
- `unsupportedBreakingChangeCount` must satisfy `max 0.0`.

Status-only certification and unauthorized external evidence must be rejected.
