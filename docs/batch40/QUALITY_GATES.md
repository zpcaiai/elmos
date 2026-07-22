# Batch 40 quality gates

Certification requires nonempty evidence, complete holdout and representative passes, zero critical findings, all evidence claims passing, and these metrics:

- `supplyChainCoverageRate` must satisfy `min 0.95`.
- `signaturePassRate` must satisfy `min 1.0`.
- `criticalVulnerabilityCount` must satisfy `max 0.0`.

Status-only certification and unauthorized external evidence must be rejected.
