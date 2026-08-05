---
name: generation-batch-g03-typed-semantic-ir
description: Typed Semantic IR与Universal Semantic Type System，FRT G03实现级Batch规范。
version: 1.0.0
batch: G03
certificate: IR0-IR6
status: implementation-ready-specification
---

# Generation Batch G03：Typed Semantic IR与Universal Semantic Type System

## 1. Mission

从：

> 框架特定AST、模板和运行结构

推进到：

> 统一为保留类型、状态、效果、身份、路由、数据和UI语义的Typed Semantic IR

本Batch必须产出可由Codex直接实施的Manifest、Schema、Runtime、API、CLI、管理端、测试、Evidence和Certificate，不允许仅停留在概念文档。

## 2. Core Capabilities

- 建立跨Vue/React/小程序/ArkUI/Flutter的类型和语义中间层
- 保留Null、Identity、Effect、Lifecycle、Navigation、Data Authority和UI语义
- 每个IR节点绑定Source Range和稳定Semantic ID
- 定义不变量、版本迁移和Schema验证

## 3. Inputs

- G2 Repository Model与各源AST/模板/元数据

## 4. Outputs

- Typed Semantic IR Bundle
- Universal Type Graph
- Invariant Set
- Provenance Map
- IR Validation Certificate

## 5. Global Hard Rules

- Source repository is read-only; generation, build, tests, mutation and repair run in isolated worktrees or sandboxes.
- Models propose candidates only; compilers, type checkers, formal kernels, independent tests and runtime evidence decide acceptance.
- No silent semantic loss, fake success, empty catch, fixed return, disabled assertion or UI-only authorization is permitted.
- All R4/R5 gates are non-compensatory; a critical failure cannot be hidden by aggregate scores.
- Every authoritative output binds input digests, toolchain, policy, environment, execution and evidence lineage.
- Unknown semantics must stop, emit a typed gap, request a product decision or escalate to a human reviewer.

## 6. Skills

- **FRT-0300 — Semantic IR Orchestrator** — [`skills/frt-0300-semantic-ir-orchestrator/SKILL.md`](../../skills/frt-0300-semantic-ir-orchestrator/SKILL.md)
- **FRT-0301 — Universal Semantic Type System** — [`skills/frt-0301-universal-semantic-type-system/SKILL.md`](../../skills/frt-0301-universal-semantic-type-system/SKILL.md)
- **FRT-0302 — Symbol Scope and Reference Graph** — [`skills/frt-0302-symbol-scope-and-reference-graph/SKILL.md`](../../skills/frt-0302-symbol-scope-and-reference-graph/SKILL.md)
- **FRT-0303 — Component Semantic IR** — [`skills/frt-0303-component-semantic-ir/SKILL.md`](../../skills/frt-0303-component-semantic-ir/SKILL.md)
- **FRT-0304 — State Effect and Lifecycle IR** — [`skills/frt-0304-state-effect-and-lifecycle-ir/SKILL.md`](../../skills/frt-0304-state-effect-and-lifecycle-ir/SKILL.md)
- **FRT-0305 — Navigation Semantic IR** — [`skills/frt-0305-navigation-semantic-ir/SKILL.md`](../../skills/frt-0305-navigation-semantic-ir/SKILL.md)
- **FRT-0306 — Data Network and Storage IR** — [`skills/frt-0306-data-network-and-storage-ir/SKILL.md`](../../skills/frt-0306-data-network-and-storage-ir/SKILL.md)
- **FRT-0307 — UI Layout and Style IR** — [`skills/frt-0307-ui-layout-and-style-ir/SKILL.md`](../../skills/frt-0307-ui-layout-and-style-ir/SKILL.md)
- **FRT-0308 — Platform Capability IR** — [`skills/frt-0308-platform-capability-ir/SKILL.md`](../../skills/frt-0308-platform-capability-ir/SKILL.md)
- **FRT-0309 — Source Location and Provenance IR** — [`skills/frt-0309-source-location-and-provenance-ir/SKILL.md`](../../skills/frt-0309-source-location-and-provenance-ir/SKILL.md)
- **FRT-0310 — Semantic Invariant Registry** — [`skills/frt-0310-semantic-invariant-registry/SKILL.md`](../../skills/frt-0310-semantic-invariant-registry/SKILL.md)
- **FRT-0311 — IR Versioning and Migration** — [`skills/frt-0311-ir-versioning-and-migration/SKILL.md`](../../skills/frt-0311-ir-versioning-and-migration/SKILL.md)
- **FRT-0312 — Semantic IR Validator** — [`skills/frt-0312-semantic-ir-validator/SKILL.md`](../../skills/frt-0312-semantic-ir-validator/SKILL.md)

## 7. Orchestration Workflow

1. Validate prerequisite batch certificates, versions, digests and compatibility contracts.
2. Resolve the exact project, tenant, workspace, source snapshot, target profile, packs, policy and environment.
3. Compile batch-specific typed contracts and obligations before changing code or state.
4. Execute deterministic and independently verifiable steps first.
5. Use restricted agent proposals only for bounded unresolved work; never permit direct certification.
6. Run positive, negative, adversarial, mutation and recovery verification appropriate to risk.
7. Store all artifacts and findings in the evidence graph with immutable digests.
8. Stop on any R4/R5 blocker and create an actionable escalation packet.
9. Issue the G03 certificate only when every mandatory gate passes.

## 8. Common Implementation Surfaces

```text
packages/contracts/g03/
packages/runtime/g03/
services/control-plane/g03/
services/workers/g03/
apps/web-console/src/features/g03/
apps/admin-console/src/features/g03/
tests/g03/
evidence/g03/
```

## 9. Batch API

```text
POST /v1/generation-batches/g03/runs
GET  /v1/generation-batches/g03/runs/{run_id}
POST /v1/generation-batches/g03/runs/{run_id}/plan
POST /v1/generation-batches/g03/runs/{run_id}/start
POST /v1/generation-batches/g03/runs/{run_id}/pause
POST /v1/generation-batches/g03/runs/{run_id}/resume
POST /v1/generation-batches/g03/runs/{run_id}/cancel
GET  /v1/generation-batches/g03/runs/{run_id}/evidence
POST /v1/generation-batches/g03/runs/{run_id}/certify
```

## 10. CLI

```bash
frt batch g03 plan --project <project> --release <release>
frt batch g03 run --plan <plan>
frt batch g03 verify --run <run-id>
frt batch g03 certify --run <run-id> --level IR5
```

## 11. Verification

- Schema validation and compatibility tests.
- Unit and component tests for deterministic logic.
- API, event, data and permission contract tests.
- End-to-end positive, failure, cancellation, retry and recovery journeys.
- Mutation and adversarial tests for critical invariants.
- Evidence digest, lineage, certificate invalidation and reproducibility tests.

## 12. Release Gates

- [ ] 关键源符号均映射到IR或Gap
- [ ] 未知类型不得静默降级为Any/Dynamic
- [ ] Effect、Lifecycle和Identity语义显式
- [ ] IR Schema和版本可迁移
- [ ] IR Round-trip与Invariant测试通过

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
- A valid `IR5` or policy-approved lower certificate is issued for the exact scope.
