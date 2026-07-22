# ELMOS Project Synthesis Engine — Batch 57–60

This package completes the first production-execution layer after the Java, Python, C#/.NET and integration packs.

## Included

- Batch 57 — Frontend and Full-stack: PG125–PG134
- Batch 58 — Test Generation: PG135–PG146
- Batch 59 — Build, Run, Diagnose, and Repair: PG147–PG158
- Batch 60 — DevSecOps, Deployment, Observability, and Recovery: PG159–PG170

Total: **46 implementation-grade Skills**.

## Product Execution Chain

```text
Approved Backend + Integration Generation
        ↓
Frontend / SDK / Auth / Forms / Navigation / State
        ↓
Full-stack Wiring
        ↓
Requirement-derived Test Intent
        ↓
Unit / Integration / Contract / Migration / E2E / Security / Performance Tests
        ↓
Clean Isolated Build
        ↓
Startup / Health / Smoke
        ↓
Diagnose / Bounded Repair / Regression
        ↓
Build Green Evidence
        ↓
CI / Security / Container / Kubernetes / IaC
        ↓
Telemetry / SLO / Release / Canary / Rollback / DR
```

## Non-negotiable Certification Rules

1. Tests originate from approved acceptance criteria, not only generated implementation.
2. Database and broker semantics use compatible real services for certification.
3. Build evidence comes from clean isolated runners.
4. Repair cannot delete tests, weaken assertions, change approved contracts, or overwrite user-owned code.
5. Build Green requires build, tests, startup, health, smoke, and required matrix evidence.
6. CI actions, dependencies, images, and artifacts are pinned and provenance-checked.
7. Containers run non-root and are signed with attached SBOM.
8. Kubernetes resources pass schema and policy validation.
9. Rollout has metric gates and automated abort.
10. Backups, restore, rollback/forward recovery, replay, and DR are exercised rather than merely documented.
