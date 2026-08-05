---
name: generation-batch-g06-target-architecture-synthesis
description: 六类Target Architecture Synthesizer与可构建Skeleton，FRT G06实现级Batch规范。
version: 1.0.0
batch: G06
certificate: TA0-TA6
status: implementation-ready-specification
---

# Generation Batch G06：六类Target Architecture Synthesizer与可构建Skeleton

## 1. Mission

从：

> 冻结Migration Plan与Typed Semantic IR

推进到：

> 生成符合目标生态习惯、可启动、可构建的目标架构和工程骨架

本Batch必须产出可由Codex直接实施的Manifest、Schema、Runtime、API、CLI、管理端、测试、Evidence和Certificate，不允许仅停留在概念文档。

## 2. Core Capabilities

- 按目标生态生成模块、路由、状态、DI、配置和Build边界
- 禁止机械复制源目录结构
- 锁定目标版本、依赖和工具链
- 输出可启动Skeleton和Architecture Decision

## 3. Inputs

- G5 Migration Plan、Target Profile、Framework/Enterprise Packs

## 4. Outputs

- Target Architecture IR
- Module Graph
- Project Layout
- Dependency Lock Plan
- Buildable Skeleton
- Architecture Certificate

## 5. Global Hard Rules

- Source repository is read-only; generation, build, tests, mutation and repair run in isolated worktrees or sandboxes.
- Models propose candidates only; compilers, type checkers, formal kernels, independent tests and runtime evidence decide acceptance.
- No silent semantic loss, fake success, empty catch, fixed return, disabled assertion or UI-only authorization is permitted.
- All R4/R5 gates are non-compensatory; a critical failure cannot be hidden by aggregate scores.
- Every authoritative output binds input digests, toolchain, policy, environment, execution and evidence lineage.
- Unknown semantics must stop, emit a typed gap, request a product decision or escalate to a human reviewer.

## 6. Skills

- **FRT-0600 — Target Architecture Orchestrator** — [`skills/frt-0600-target-architecture-orchestrator/SKILL.md`](../../skills/frt-0600-target-architecture-orchestrator/SKILL.md)
- **FRT-0601 — Vue 2 Architecture Synthesizer** — [`skills/frt-0601-vue-2-architecture-synthesizer/SKILL.md`](../../skills/frt-0601-vue-2-architecture-synthesizer/SKILL.md)
- **FRT-0602 — Vue 3 Architecture Synthesizer** — [`skills/frt-0602-vue-3-architecture-synthesizer/SKILL.md`](../../skills/frt-0602-vue-3-architecture-synthesizer/SKILL.md)
- **FRT-0603 — React Architecture Synthesizer** — [`skills/frt-0603-react-architecture-synthesizer/SKILL.md`](../../skills/frt-0603-react-architecture-synthesizer/SKILL.md)
- **FRT-0604 — WeChat Mini Program Architecture Synthesizer** — [`skills/frt-0604-wechat-mini-program-architecture-synthesizer/SKILL.md`](../../skills/frt-0604-wechat-mini-program-architecture-synthesizer/SKILL.md)
- **FRT-0605 — ArkUI Architecture Synthesizer** — [`skills/frt-0605-arkui-architecture-synthesizer/SKILL.md`](../../skills/frt-0605-arkui-architecture-synthesizer/SKILL.md)
- **FRT-0606 — Flutter Architecture Synthesizer** — [`skills/frt-0606-flutter-architecture-synthesizer/SKILL.md`](../../skills/frt-0606-flutter-architecture-synthesizer/SKILL.md)
- **FRT-0607 — Target Module Boundary Synthesizer** — [`skills/frt-0607-target-module-boundary-synthesizer/SKILL.md`](../../skills/frt-0607-target-module-boundary-synthesizer/SKILL.md)
- **FRT-0608 — Dependency and Toolchain Resolver** — [`skills/frt-0608-dependency-and-toolchain-resolver/SKILL.md`](../../skills/frt-0608-dependency-and-toolchain-resolver/SKILL.md)
- **FRT-0609 — Project Layout Generator** — [`skills/frt-0609-project-layout-generator/SKILL.md`](../../skills/frt-0609-project-layout-generator/SKILL.md)
- **FRT-0610 — Buildable Skeleton Generator** — [`skills/frt-0610-buildable-skeleton-generator/SKILL.md`](../../skills/frt-0610-buildable-skeleton-generator/SKILL.md)
- **FRT-0611 — Bootstrap and Smoke Validator** — [`skills/frt-0611-bootstrap-and-smoke-validator/SKILL.md`](../../skills/frt-0611-bootstrap-and-smoke-validator/SKILL.md)
- **FRT-0612 — Target Architecture Certification** — [`skills/frt-0612-target-architecture-certification/SKILL.md`](../../skills/frt-0612-target-architecture-certification/SKILL.md)

## 7. Orchestration Workflow

1. Validate prerequisite batch certificates, versions, digests and compatibility contracts.
2. Resolve the exact project, tenant, workspace, source snapshot, target profile, packs, policy and environment.
3. Compile batch-specific typed contracts and obligations before changing code or state.
4. Execute deterministic and independently verifiable steps first.
5. Use restricted agent proposals only for bounded unresolved work; never permit direct certification.
6. Run positive, negative, adversarial, mutation and recovery verification appropriate to risk.
7. Store all artifacts and findings in the evidence graph with immutable digests.
8. Stop on any R4/R5 blocker and create an actionable escalation packet.
9. Issue the G06 certificate only when every mandatory gate passes.

## 8. Common Implementation Surfaces

```text
packages/contracts/g06/
packages/runtime/g06/
services/control-plane/g06/
services/workers/g06/
apps/web-console/src/features/g06/
apps/admin-console/src/features/g06/
tests/g06/
evidence/g06/
```

## 9. Batch API

```text
POST /v1/generation-batches/g06/runs
GET  /v1/generation-batches/g06/runs/{run_id}
POST /v1/generation-batches/g06/runs/{run_id}/plan
POST /v1/generation-batches/g06/runs/{run_id}/start
POST /v1/generation-batches/g06/runs/{run_id}/pause
POST /v1/generation-batches/g06/runs/{run_id}/resume
POST /v1/generation-batches/g06/runs/{run_id}/cancel
GET  /v1/generation-batches/g06/runs/{run_id}/evidence
POST /v1/generation-batches/g06/runs/{run_id}/certify
```

## 10. CLI

```bash
frt batch g06 plan --project <project> --release <release>
frt batch g06 run --plan <plan>
frt batch g06 verify --run <run-id>
frt batch g06 certify --run <run-id> --level TA5
```

## 11. Verification

- Schema validation and compatibility tests.
- Unit and component tests for deterministic logic.
- API, event, data and permission contract tests.
- End-to-end positive, failure, cancellation, retry and recovery journeys.
- Mutation and adversarial tests for critical invariants.
- Evidence digest, lineage, certificate invalidation and reproducibility tests.

## 12. Release Gates

- [ ] 目标依赖图无未批准循环
- [ ] Skeleton在干净环境可安装、Typecheck和启动
- [ ] 版本和Lockfile由真实工具生成
- [ ] Critical能力均有目标模块Owner
- [ ] 目标架构不泄漏源框架惯用法

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
- A valid `TA5` or policy-approved lower certificate is issued for the exact scope.
