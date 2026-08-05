---
name: generation-batch-g08-component-semantics
description: Component、Props、Events、Slots、Hooks、Context与Identity语义，FRT G08实现级Batch规范。
version: 1.0.0
batch: G08
certificate: CS0-CS6
status: implementation-ready-specification
---

# Generation Batch G08：Component、Props、Events、Slots、Hooks、Context与Identity语义

## 1. Mission

从：

> 框架中立组件IR

推进到：

> 在目标框架中保持组件边界、输入输出、Identity和测试语义

本Batch必须产出可由Codex直接实施的Manifest、Schema、Runtime、API、CLI、管理端、测试、Evidence和Certificate，不允许仅停留在概念文档。

## 2. Core Capabilities

- 保持Props默认值、事件时机、Slot/Children/Builder结构
- 保持Key、Ref、Widget Identity和状态保留语义
- 正确降低Hooks、Composable、Context和局部状态
- 生成目标Component Tests与差分Oracle

## 3. Inputs

- Component Semantic IR、Target Component Profile

## 4. Outputs

- Component Mapping Plan
- Target Components
- Identity Map
- Component Tests
- Component Certificate

## 5. Global Hard Rules

- Source repository is read-only; generation, build, tests, mutation and repair run in isolated worktrees or sandboxes.
- Models propose candidates only; compilers, type checkers, formal kernels, independent tests and runtime evidence decide acceptance.
- No silent semantic loss, fake success, empty catch, fixed return, disabled assertion or UI-only authorization is permitted.
- All R4/R5 gates are non-compensatory; a critical failure cannot be hidden by aggregate scores.
- Every authoritative output binds input digests, toolchain, policy, environment, execution and evidence lineage.
- Unknown semantics must stop, emit a typed gap, request a product decision or escalate to a human reviewer.

## 6. Skills

- **FRT-0800 — Component Semantics Orchestrator** — [`skills/frt-0800-component-semantics-orchestrator/SKILL.md`](../../skills/frt-0800-component-semantics-orchestrator/SKILL.md)
- **FRT-0801 — Component Boundary Mapper** — [`skills/frt-0801-component-boundary-mapper/SKILL.md`](../../skills/frt-0801-component-boundary-mapper/SKILL.md)
- **FRT-0802 — Props and Input Contract Mapper** — [`skills/frt-0802-props-and-input-contract-mapper/SKILL.md`](../../skills/frt-0802-props-and-input-contract-mapper/SKILL.md)
- **FRT-0803 — Events Callback and Emit Mapper** — [`skills/frt-0803-events-callback-and-emit-mapper/SKILL.md`](../../skills/frt-0803-events-callback-and-emit-mapper/SKILL.md)
- **FRT-0804 — Slots Children and Builder Mapper** — [`skills/frt-0804-slots-children-and-builder-mapper/SKILL.md`](../../skills/frt-0804-slots-children-and-builder-mapper/SKILL.md)
- **FRT-0805 — Refs Keys and Identity Mapper** — [`skills/frt-0805-refs-keys-and-identity-mapper/SKILL.md`](../../skills/frt-0805-refs-keys-and-identity-mapper/SKILL.md)
- **FRT-0806 — Hooks Composables and Context Mapper** — [`skills/frt-0806-hooks-composables-and-context-mapper/SKILL.md`](../../skills/frt-0806-hooks-composables-and-context-mapper/SKILL.md)
- **FRT-0807 — Controlled and Uncontrolled State Mapper** — [`skills/frt-0807-controlled-and-uncontrolled-state-mapper/SKILL.md`](../../skills/frt-0807-controlled-and-uncontrolled-state-mapper/SKILL.md)
- **FRT-0808 — Component Lifecycle Mapper** — [`skills/frt-0808-component-lifecycle-mapper/SKILL.md`](../../skills/frt-0808-component-lifecycle-mapper/SKILL.md)
- **FRT-0809 — Portal Teleport and Overlay Mapper** — [`skills/frt-0809-portal-teleport-and-overlay-mapper/SKILL.md`](../../skills/frt-0809-portal-teleport-and-overlay-mapper/SKILL.md)
- **FRT-0810 — Dynamic Component Mapper** — [`skills/frt-0810-dynamic-component-mapper/SKILL.md`](../../skills/frt-0810-dynamic-component-mapper/SKILL.md)
- **FRT-0811 — Component Test Generator** — [`skills/frt-0811-component-test-generator/SKILL.md`](../../skills/frt-0811-component-test-generator/SKILL.md)
- **FRT-0812 — Component Semantics Certification** — [`skills/frt-0812-component-semantics-certification/SKILL.md`](../../skills/frt-0812-component-semantics-certification/SKILL.md)

## 7. Orchestration Workflow

1. Validate prerequisite batch certificates, versions, digests and compatibility contracts.
2. Resolve the exact project, tenant, workspace, source snapshot, target profile, packs, policy and environment.
3. Compile batch-specific typed contracts and obligations before changing code or state.
4. Execute deterministic and independently verifiable steps first.
5. Use restricted agent proposals only for bounded unresolved work; never permit direct certification.
6. Run positive, negative, adversarial, mutation and recovery verification appropriate to risk.
7. Store all artifacts and findings in the evidence graph with immutable digests.
8. Stop on any R4/R5 blocker and create an actionable escalation packet.
9. Issue the G08 certificate only when every mandatory gate passes.

## 8. Common Implementation Surfaces

```text
packages/contracts/g08/
packages/runtime/g08/
services/control-plane/g08/
services/workers/g08/
apps/web-console/src/features/g08/
apps/admin-console/src/features/g08/
tests/g08/
evidence/g08/
```

## 9. Batch API

```text
POST /v1/generation-batches/g08/runs
GET  /v1/generation-batches/g08/runs/{run_id}
POST /v1/generation-batches/g08/runs/{run_id}/plan
POST /v1/generation-batches/g08/runs/{run_id}/start
POST /v1/generation-batches/g08/runs/{run_id}/pause
POST /v1/generation-batches/g08/runs/{run_id}/resume
POST /v1/generation-batches/g08/runs/{run_id}/cancel
GET  /v1/generation-batches/g08/runs/{run_id}/evidence
POST /v1/generation-batches/g08/runs/{run_id}/certify
```

## 10. CLI

```bash
frt batch g08 plan --project <project> --release <release>
frt batch g08 run --plan <plan>
frt batch g08 verify --run <run-id>
frt batch g08 certify --run <run-id> --level CS5
```

## 11. Verification

- Schema validation and compatibility tests.
- Unit and component tests for deterministic logic.
- API, event, data and permission contract tests.
- End-to-end positive, failure, cancellation, retry and recovery journeys.
- Mutation and adversarial tests for critical invariants.
- Evidence digest, lineage, certificate invalidation and reproducibility tests.

## 12. Release Gates

- [ ] 关键组件输入输出Contract完整
- [ ] Key/Identity变化无未批准状态丢失
- [ ] Slot/Children语义不被机械扁平化
- [ ] Lifecycle和Cleanup测试通过
- [ ] 动态组件未知路径显式登记

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
- A valid `CS5` or policy-approved lower certificate is issued for the exact scope.
