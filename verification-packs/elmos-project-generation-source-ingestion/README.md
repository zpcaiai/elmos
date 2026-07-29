# ELMOS project-generation source-ingestion verification

Exact Batch 35 experimental pack for the Web Console source-ingestion boundary.
It binds production code and tests by SHA-256 and records nine locally executed
tests covering parser formats, limits, Skill isolation, SSRF address policy,
provenance, seeded fuzzing, two mutation negative controls, holdout cases, and
repository-owned representative workloads.

Replay:

```bash
pnpm --dir apps/web-console exec playwright test \
  --project=chromium e2e/generation-source-ingestion.spec.ts
python scripts/batch35/validate_verification_pack.py \
  verification-packs/elmos-project-generation-source-ingestion
python scripts/batch35/run_verification_gate.py \
  verification-packs/elmos-project-generation-source-ingestion
```

The expected gate decision is `NOT_CERTIFIED`. External security execution,
independent verification, and production workload evidence remain `NOT_RUN`.
