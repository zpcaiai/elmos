# ELMOS project-generation source-ingestion verification

Exact Batch 35 limited pack for the Web Console source-ingestion boundary.
It binds production code and tests by SHA-256 and records ten locally executed
tests covering parser formats, limits, Skill isolation, SSRF address policy,
provenance, expired-bundle quota reclamation, seeded fuzzing, two mutation
negative controls, holdout cases, and repository-owned representative workloads.
All declared local evidence and verification contracts are now byte-counted and
SHA-256-bound; evidence and profile tampering are covered by negative toolkit
tests. The gate emits machine-readable certification blockers even when the pack
is not requesting certification. `limited` applies only to this exact local,
deterministic scope and does not change the certification decision.

Replay:

```bash
pnpm --dir apps/web-console exec playwright test \
  --project=chromium e2e/generation-source-ingestion.spec.ts
python scripts/batch35/validate_verification_pack.py \
  verification-packs/elmos-project-generation-source-ingestion
python scripts/batch35/run_verification_gate.py \
  verification-packs/elmos-project-generation-source-ingestion
```

The expected gate decision is `NOT_CERTIFIED` with readiness `BLOCKED`. External
security execution, independent verification, and production workload evidence
remain `NOT_RUN`; these records cannot be manufactured by a local run.
