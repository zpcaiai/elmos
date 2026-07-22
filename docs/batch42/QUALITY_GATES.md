# Batch 42 quality gates

Certification requires nonempty evidence, complete holdout and representative passes, zero critical findings, all evidence claims passing, and these metrics:

- `agentEvalPassRate` must satisfy `min 1.0`.
- `policyViolationCount` must satisfy `max 0.0`.
- `killSwitchPassRate` must satisfy `min 1.0`.

Status-only certification and unauthorized external evidence must be rejected.
