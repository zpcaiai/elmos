# Rule / Skill / Model Promotion Policy

A production trajectory may create a **candidate**, never a directly trusted production change.

Promotion stages:
1. Candidate extracted with source trajectory and failure attribution.
2. Unit/regression fixture passes.
3. Historical corpus replay: no critical regression.
4. Golden-route corpus: meets route thresholds.
5. Security/policy review for capability expansion.
6. Shadow execution against production-like tasks.
7. Canary cohort with automatic rollback thresholds.
8. Stable promotion with immutable version and provenance.

Required comparison dimensions: correctness, evidence completeness, latency, cost, failure recovery, security boundary violations, false-positive/false-negative rates where applicable.
