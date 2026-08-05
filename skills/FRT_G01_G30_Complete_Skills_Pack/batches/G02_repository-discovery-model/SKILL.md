---
name: generation-batch-g02-repository-discovery-model
description: Repository Discovery、技术识别、依赖图与可迁移仓库模型，FRT G02实现级Batch规范。
version: 1.0.0
batch: G02
certificate: RM0-RM6
status: implementation-ready-specification
---

# Generation Batch G02：Repository Discovery、技术识别、依赖图与可迁移仓库模型

## 1. Mission

从：

> 一个未知大型前端仓库

推进到：

> 形成可查询、可追踪、可认证的Repository Model与风险清单

本Batch必须产出可由Codex直接实施的Manifest、Schema、Runtime、API、CLI、管理端、测试、Evidence和Certificate，不允许仅停留在概念文档。

## 2. Core Capabilities

- 识别Monorepo、Package、Framework、Runtime和Build链
- 建立模块、依赖、路由、组件、状态、API、存储和资产清单
- 检测动态代码、原生能力、平台限制和迁移风险
- 输出稳定Repository Model及Source Location Map

## 3. Inputs

- 只读源仓库Snapshot
- 允许的解析器、构建工具和网络策略

## 4. Outputs

- Repository Model
- Dependency Graph
- Route/Component/State/API Inventories
- Risk Register
- Discovery Certificate

## 5. Global Hard Rules

- Source repository is read-only; generation, build, tests, mutation and repair run in isolated worktrees or sandboxes.
- Models propose candidates only; compilers, type checkers, formal kernels, independent tests and runtime evidence decide acceptance.
- No silent semantic loss, fake success, empty catch, fixed return, disabled assertion or UI-only authorization is permitted.
- All R4/R5 gates are non-compensatory; a critical failure cannot be hidden by aggregate scores.
- Every authoritative output binds input digests, toolchain, policy, environment, execution and evidence lineage.
- Unknown semantics must stop, emit a typed gap, request a product decision or escalate to a human reviewer.

## 6. Skills

- **FRT-0200 — Repository Discovery Orchestrator** — [`skills/frt-0200-repository-discovery-orchestrator/SKILL.md`](../../skills/frt-0200-repository-discovery-orchestrator/SKILL.md)
- **FRT-0201 — Workspace and Package Detector** — [`skills/frt-0201-workspace-and-package-detector/SKILL.md`](../../skills/frt-0201-workspace-and-package-detector/SKILL.md)
- **FRT-0202 — Framework and Version Detector** — [`skills/frt-0202-framework-and-version-detector/SKILL.md`](../../skills/frt-0202-framework-and-version-detector/SKILL.md)
- **FRT-0203 — Build Toolchain Detector** — [`skills/frt-0203-build-toolchain-detector/SKILL.md`](../../skills/frt-0203-build-toolchain-detector/SKILL.md)
- **FRT-0204 — Dependency Graph Builder** — [`skills/frt-0204-dependency-graph-builder/SKILL.md`](../../skills/frt-0204-dependency-graph-builder/SKILL.md)
- **FRT-0205 — Module Boundary Analyzer** — [`skills/frt-0205-module-boundary-analyzer/SKILL.md`](../../skills/frt-0205-module-boundary-analyzer/SKILL.md)
- **FRT-0206 — Route and Page Inventory** — [`skills/frt-0206-route-and-page-inventory/SKILL.md`](../../skills/frt-0206-route-and-page-inventory/SKILL.md)
- **FRT-0207 — Component Inventory** — [`skills/frt-0207-component-inventory/SKILL.md`](../../skills/frt-0207-component-inventory/SKILL.md)
- **FRT-0208 — State and Store Inventory** — [`skills/frt-0208-state-and-store-inventory/SKILL.md`](../../skills/frt-0208-state-and-store-inventory/SKILL.md)
- **FRT-0209 — API Event and Storage Inventory** — [`skills/frt-0209-api-event-and-storage-inventory/SKILL.md`](../../skills/frt-0209-api-event-and-storage-inventory/SKILL.md)
- **FRT-0210 — Asset I18n and Accessibility Inventory** — [`skills/frt-0210-asset-i18n-and-accessibility-inventory/SKILL.md`](../../skills/frt-0210-asset-i18n-and-accessibility-inventory/SKILL.md)
- **FRT-0211 — Repository Risk Classifier** — [`skills/frt-0211-repository-risk-classifier/SKILL.md`](../../skills/frt-0211-repository-risk-classifier/SKILL.md)
- **FRT-0212 — Repository Model Certification** — [`skills/frt-0212-repository-model-certification/SKILL.md`](../../skills/frt-0212-repository-model-certification/SKILL.md)

## 7. Orchestration Workflow

1. Validate prerequisite batch certificates, versions, digests and compatibility contracts.
2. Resolve the exact project, tenant, workspace, source snapshot, target profile, packs, policy and environment.
3. Compile batch-specific typed contracts and obligations before changing code or state.
4. Execute deterministic and independently verifiable steps first.
5. Use restricted agent proposals only for bounded unresolved work; never permit direct certification.
6. Run positive, negative, adversarial, mutation and recovery verification appropriate to risk.
7. Store all artifacts and findings in the evidence graph with immutable digests.
8. Stop on any R4/R5 blocker and create an actionable escalation packet.
9. Issue the G02 certificate only when every mandatory gate passes.

## 8. Common Implementation Surfaces

```text
packages/contracts/g02/
packages/runtime/g02/
services/control-plane/g02/
services/workers/g02/
apps/web-console/src/features/g02/
apps/admin-console/src/features/g02/
tests/g02/
evidence/g02/
```

## 9. Batch API

```text
POST /v1/generation-batches/g02/runs
GET  /v1/generation-batches/g02/runs/{run_id}
POST /v1/generation-batches/g02/runs/{run_id}/plan
POST /v1/generation-batches/g02/runs/{run_id}/start
POST /v1/generation-batches/g02/runs/{run_id}/pause
POST /v1/generation-batches/g02/runs/{run_id}/resume
POST /v1/generation-batches/g02/runs/{run_id}/cancel
GET  /v1/generation-batches/g02/runs/{run_id}/evidence
POST /v1/generation-batches/g02/runs/{run_id}/certify
```

## 10. CLI

```bash
frt batch g02 plan --project <project> --release <release>
frt batch g02 run --plan <plan>
frt batch g02 verify --run <run-id>
frt batch g02 certify --run <run-id> --level RM5
```

## 11. Verification

- Schema validation and compatibility tests.
- Unit and component tests for deterministic logic.
- API, event, data and permission contract tests.
- End-to-end positive, failure, cancellation, retry and recovery journeys.
- Mutation and adversarial tests for critical invariants.
- Evidence digest, lineage, certificate invalidation and reproducibility tests.

## 12. Release Gates

- [ ] 所有可构建Package均已识别
- [ ] Framework和版本未知项显式登记
- [ ] 关键路由、组件、Store、API和平台能力覆盖率达到策略
- [ ] 解析不执行不可信仓库代码
- [ ] 所有发现可追溯到Source Range

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
- A valid `RM5` or policy-approved lower certificate is issued for the exact scope.
