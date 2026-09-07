---
name: migration-pack-m29-m34-integration
description: "Integrate or review Migration Pack Certification M29-M34 assets, Skills, schemas, deterministic tooling, admission APIs and gate boundaries. Use when changing route, framework, database, client, cloud or portfolio certification integration."
---

# Migration Pack M29-M34 Integration

## Namespace

Use `M29` through `M34` in product code and documentation. These packs are independent from ELMOS Product Batches 29-34.

## Read first

- `AGENTS.md`
- `docs/batch29/` through `docs/batch34/`
- `.agents/skills/b29-*/SKILL.md` through `.agents/skills/b34-*/SKILL.md`
- `schemas/batch29/` through `schemas/batch34/`
- `scripts/batch29/` through `scripts/batch34/`
- `modules/migration-pack-certification/`

## Required boundaries

1. Use the smallest applicable `$b29-*` through `$b34-*` Skill.
2. Require exact direction, versions, immutable source and target snapshots, tenant and toolchain scope.
3. Require typed IR/contracts, real source/target environments, independent holdout evidence and default-deny networking.
4. Never hide unsupported semantics, inaccessible repositories or failed workloads.
5. Never broaden IAM, egress, public exposure, data access or permissions to pass a gate.
6. The Java admission API may only return `BLOCKED` or `READY_FOR_PACK_GATE`.
7. Only the exact `scripts/batchXX/run_*_gate.py` named by the pack can determine certification readiness.

## Verification

Run each batch test directory separately to preserve test-module isolation. Validate all schemas, templates, imported Skills and `agents/openai.yaml`. A structurally passing toolkit is not a certified route, framework, database, client, cloud or portfolio pack; real certification stays `NOT_RUN` without external evidence.
