# Batch 41 quality gates

Certification requires nonempty evidence, complete holdout and representative passes, zero critical findings, all evidence claims passing, and these metrics:

- `knowledgeProvenanceCoverageRate` must satisfy `min 0.95`.
- `privacyIsolationPassRate` must satisfy `min 1.0`.
- `predictionCalibrationPassRate` must satisfy `min 1.0`.

Status-only certification and unauthorized external evidence must be rejected.
