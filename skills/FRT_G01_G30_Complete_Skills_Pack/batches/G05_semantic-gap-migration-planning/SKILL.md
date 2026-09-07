---
name: generation-batch-g05-semantic-gap-migration-planning
description: Semantic Gap、兼容性评估、Product Decision与Migration Plan，FRT G05实现级Batch规范。
version: 1.0.0
batch: G05
certificate: MP0-MP6
status: implementation-ready-specification
---

# Generation Batch G05：Semantic Gap、兼容性评估、Product Decision与Migration Plan

## 1. Mission

从：

> 已恢复的源语义与候选目标能力

推进到：

> 形成显式Gap、风险、Shim、人工决策和冻结的可执行迁移计划

本Batch必须产出可由Codex直接实施的Manifest、Schema、Runtime、API、CLI、管理端、测试、Evidence和Certificate，不允许仅停留在概念文档。

## 2. Core Capabilities

- 比较源语义与目标能力并生成Gap Register
- 区分Native、Shim、Product Decision、Manual与Unsupported
- 估算正确率、耗时、风险、数据和测试影响
- 生成多Pass可恢复Migration Plan并冻结Digest

## 3. Inputs

- G3 IR、G4 Adapter结果、目标Profile和Pack候选

## 4. Outputs

- Compatibility Assessment
- Semantic Gap Register
- Product Decision Set
- Shim/Manual Plans
- Frozen Migration Plan
- Plan Certificate

## 5. Global Hard Rules

- Source repository is read-only; generation, build, tests, mutation and repair run in isolated worktrees or sandboxes.
- Models propose candidates only; compilers, type checkers, formal kernels, independent tests and runtime evidence decide acceptance.
- No silent semantic loss, fake success, empty catch, fixed return, disabled assertion or UI-only authorization is permitted.
- All R4/R5 gates are non-compensatory; a critical failure cannot be hidden by aggregate scores.
- Every authoritative output binds input digests, toolchain, policy, environment, execution and evidence lineage.
- Unknown semantics must stop, emit a typed gap, request a product decision or escalate to a human reviewer.

## 6. Skills

- **FRT-0500 — Migration Planning Orchestrator** — [`skills/frt-0500-migration-planning-orchestrator/SKILL.md`](../../skills/frt-0500-migration-planning-orchestrator/SKILL.md)
- **FRT-0501 — Semantic Gap Detector** — [`skills/frt-0501-semantic-gap-detector/SKILL.md`](../../skills/frt-0501-semantic-gap-detector/SKILL.md)
- **FRT-0502 — Capability Compatibility Matrix** — [`skills/frt-0502-capability-compatibility-matrix/SKILL.md`](../../skills/frt-0502-capability-compatibility-matrix/SKILL.md)
- **FRT-0503 — Source Target Feature Mapper** — [`skills/frt-0503-source-target-feature-mapper/SKILL.md`](../../skills/frt-0503-source-target-feature-mapper/SKILL.md)
- **FRT-0504 — Product Decision Generator** — [`skills/frt-0504-product-decision-generator/SKILL.md`](../../skills/frt-0504-product-decision-generator/SKILL.md)
- **FRT-0505 — Shim Requirement Planner** — [`skills/frt-0505-shim-requirement-planner/SKILL.md`](../../skills/frt-0505-shim-requirement-planner/SKILL.md)
- **FRT-0506 — Manual Boundary Planner** — [`skills/frt-0506-manual-boundary-planner/SKILL.md`](../../skills/frt-0506-manual-boundary-planner/SKILL.md)
- **FRT-0507 — Risk Confidence and Criticality Scorer** — [`skills/frt-0507-risk-confidence-and-criticality-scorer/SKILL.md`](../../skills/frt-0507-risk-confidence-and-criticality-scorer/SKILL.md)
- **FRT-0508 — Migration Effort and Duration Estimator** — [`skills/frt-0508-migration-effort-and-duration-estimator/SKILL.md`](../../skills/frt-0508-migration-effort-and-duration-estimator/SKILL.md)
- **FRT-0509 — Multi-Pass Migration Plan Generator** — [`skills/frt-0509-multi-pass-migration-plan-generator/SKILL.md`](../../skills/frt-0509-multi-pass-migration-plan-generator/SKILL.md)
- **FRT-0510 — Migration Plan Freezer** — [`skills/frt-0510-migration-plan-freezer/SKILL.md`](../../skills/frt-0510-migration-plan-freezer/SKILL.md)
- **FRT-0511 — Plan Explainability Generator** — [`skills/frt-0511-plan-explainability-generator/SKILL.md`](../../skills/frt-0511-plan-explainability-generator/SKILL.md)
- **FRT-0512 — Migration Plan Certification** — [`skills/frt-0512-migration-plan-certification/SKILL.md`](../../skills/frt-0512-migration-plan-certification/SKILL.md)

## 7. Orchestration Workflow

1. Validate prerequisite batch certificates, versions, digests and compatibility contracts.
2. Resolve the exact project, tenant, workspace, source snapshot, target profile, packs, policy and environment.
3. Compile batch-specific typed contracts and obligations before changing code or state.
4. Execute deterministic and independently verifiable steps first.
5. Use restricted agent proposals only for bounded unresolved work; never permit direct certification.
6. Run positive, negative, adversarial, mutation and recovery verification appropriate to risk.
7. Store all artifacts and findings in the evidence graph with immutable digests.
8. Stop on any R4/R5 blocker and create an actionable escalation packet.
9. Issue the G05 certificate only when every mandatory gate passes.

## 8. Common Implementation Surfaces

```text
packages/contracts/g05/
packages/runtime/g05/
services/control-plane/g05/
services/workers/g05/
apps/web-console/src/features/g05/
apps/admin-console/src/features/g05/
tests/g05/
evidence/g05/
```

## 9. Batch API

```text
POST /v1/generation-batches/g05/runs
GET  /v1/generation-batches/g05/runs/{run_id}
POST /v1/generation-batches/g05/runs/{run_id}/plan
POST /v1/generation-batches/g05/runs/{run_id}/start
POST /v1/generation-batches/g05/runs/{run_id}/pause
POST /v1/generation-batches/g05/runs/{run_id}/resume
POST /v1/generation-batches/g05/runs/{run_id}/cancel
GET  /v1/generation-batches/g05/runs/{run_id}/evidence
POST /v1/generation-batches/g05/runs/{run_id}/certify
```

## 10. CLI

```bash
frt batch g05 plan --project <project> --release <release>
frt batch g05 run --plan <plan>
frt batch g05 verify --run <run-id>
frt batch g05 certify --run <run-id> --level MP5
```

## 11. Verification

- Schema validation and compatibility tests.
- Unit and component tests for deterministic logic.
- API, event, data and permission contract tests.
- End-to-end positive, failure, cancellation, retry and recovery journeys.
- Mutation and adversarial tests for critical invariants.
- Evidence digest, lineage, certificate invalidation and reproducibility tests.

## 12. Release Gates

- [ ] 所有关键源能力均有映射或显式Gap
- [ ] Unsupported不得伪装支持
- [ ] R4/R5决策需人工批准
- [ ] Plan绑定Source Snapshot、Target Profile和Pack Lock
- [ ] 估算披露假设和不确定性

## 13. Stop and Escalate When

- A prerequisite certificate is missing, stale, revoked or out of scope.
- A critical semantic, authority, permission, data, security or recovery decision is unknown.
- The only apparent implementation requires weakening tests, policy, isolation, audit or evidence.
- The environment cannot provide the real compiler, runtime, device, provider or independent oracle required for certification.
- The requested change exceeds the approved batch or release scope.

## 14. Definition of Done

- Every listed Skill has an installable `SKILL.md` and unique ID.
- All required contracts and schemas are versioned and validated.
- Runtime, API, CLI and UI paths are implemented or explicitly marked not applicable with approved evidence.
- Positive, negative, failure, mutation and recovery tests pass.
- Findings have owners and no unresolved critical blockers remain.
- Evidence is immutable, reproducible and bound to exact digests.
- A valid `MP5` or policy-approved lower certificate is issued for the exact scope.
