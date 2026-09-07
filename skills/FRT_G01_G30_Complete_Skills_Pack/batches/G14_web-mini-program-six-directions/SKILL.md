---
name: generation-batch-g14-web-mini-program-six-directions
description: Web与微信小程序双向六条转换路径，FRT G14实现级Batch规范。
version: 1.0.0
batch: G14
certificate: WM0-WM6
status: implementation-ready-specification
---

# Generation Batch G14：Web与微信小程序双向六条转换路径

## 1. Mission

从：

> 三种Web框架和小程序平台模型

推进到：

> Vue2/Vue3/React与小程序六条方向均可生成和验证

本Batch必须产出可由Codex直接实施的Manifest、Schema、Runtime、API、CLI、管理端、测试、Evidence和Certificate，不允许仅停留在概念文档。

## 2. Core Capabilities

- 处理WXML/WXSS/setData/Page/Component与Web组件模型
- 处理分包、基础库、授权、支付、Storage和页面栈限制
- Web缺失能力和小程序限制显式Gap/Unsupported

## 3. Inputs

- G1–G12、Web/Mini Program Profiles和设备Fixture

## 4. Outputs

- 六个Web↔Mini Program Packs
- Capability Gap Plans
- Device/Differential Tests
- Route Certificates

## 5. Global Hard Rules

- Source repository is read-only; generation, build, tests, mutation and repair run in isolated worktrees or sandboxes.
- Models propose candidates only; compilers, type checkers, formal kernels, independent tests and runtime evidence decide acceptance.
- No silent semantic loss, fake success, empty catch, fixed return, disabled assertion or UI-only authorization is permitted.
- All R4/R5 gates are non-compensatory; a critical failure cannot be hidden by aggregate scores.
- Every authoritative output binds input digests, toolchain, policy, environment, execution and evidence lineage.
- Unknown semantics must stop, emit a typed gap, request a product decision or escalate to a human reviewer.

## 6. Skills

- **FRT-1400 — Web Mini Program Route Orchestrator** — [`skills/frt-1400-web-mini-program-route-orchestrator/SKILL.md`](../../skills/frt-1400-web-mini-program-route-orchestrator/SKILL.md)
- **FRT-1401 — Vue 2 to Mini Program Route Pack** — [`skills/frt-1401-vue-2-to-mini-program-route-pack/SKILL.md`](../../skills/frt-1401-vue-2-to-mini-program-route-pack/SKILL.md)
- **FRT-1402 — Mini Program to Vue 2 Route Pack** — [`skills/frt-1402-mini-program-to-vue-2-route-pack/SKILL.md`](../../skills/frt-1402-mini-program-to-vue-2-route-pack/SKILL.md)
- **FRT-1403 — Vue 3 to Mini Program Route Pack** — [`skills/frt-1403-vue-3-to-mini-program-route-pack/SKILL.md`](../../skills/frt-1403-vue-3-to-mini-program-route-pack/SKILL.md)
- **FRT-1404 — Mini Program to Vue 3 Route Pack** — [`skills/frt-1404-mini-program-to-vue-3-route-pack/SKILL.md`](../../skills/frt-1404-mini-program-to-vue-3-route-pack/SKILL.md)
- **FRT-1405 — React to Mini Program Route Pack** — [`skills/frt-1405-react-to-mini-program-route-pack/SKILL.md`](../../skills/frt-1405-react-to-mini-program-route-pack/SKILL.md)
- **FRT-1406 — Mini Program to React Route Pack** — [`skills/frt-1406-mini-program-to-react-route-pack/SKILL.md`](../../skills/frt-1406-mini-program-to-react-route-pack/SKILL.md)
- **FRT-1407 — Mini Program Capability Gap Planner** — [`skills/frt-1407-mini-program-capability-gap-planner/SKILL.md`](../../skills/frt-1407-mini-program-capability-gap-planner/SKILL.md)
- **FRT-1408 — Mini Program Route Form and Storage Mapper** — [`skills/frt-1408-mini-program-route-form-and-storage-mapper/SKILL.md`](../../skills/frt-1408-mini-program-route-form-and-storage-mapper/SKILL.md)
- **FRT-1409 — Mini Program Identity Payment and Permission Mapper** — [`skills/frt-1409-mini-program-identity-payment-and-permission-mapper/SKILL.md`](../../skills/frt-1409-mini-program-identity-payment-and-permission-mapper/SKILL.md)
- **FRT-1410 — Web Mini Program Differential Corpus** — [`skills/frt-1410-web-mini-program-differential-corpus/SKILL.md`](../../skills/frt-1410-web-mini-program-differential-corpus/SKILL.md)
- **FRT-1411 — Web Mini Program Route Certification** — [`skills/frt-1411-web-mini-program-route-certification/SKILL.md`](../../skills/frt-1411-web-mini-program-route-certification/SKILL.md)

## 7. Orchestration Workflow

1. Validate prerequisite batch certificates, versions, digests and compatibility contracts.
2. Resolve the exact project, tenant, workspace, source snapshot, target profile, packs, policy and environment.
3. Compile batch-specific typed contracts and obligations before changing code or state.
4. Execute deterministic and independently verifiable steps first.
5. Use restricted agent proposals only for bounded unresolved work; never permit direct certification.
6. Run positive, negative, adversarial, mutation and recovery verification appropriate to risk.
7. Store all artifacts and findings in the evidence graph with immutable digests.
8. Stop on any R4/R5 blocker and create an actionable escalation packet.
9. Issue the G14 certificate only when every mandatory gate passes.

## 8. Common Implementation Surfaces

```text
packages/contracts/g14/
packages/runtime/g14/
services/control-plane/g14/
services/workers/g14/
apps/web-console/src/features/g14/
apps/admin-console/src/features/g14/
tests/g14/
evidence/g14/
```

## 9. Batch API

```text
POST /v1/generation-batches/g14/runs
GET  /v1/generation-batches/g14/runs/{run_id}
POST /v1/generation-batches/g14/runs/{run_id}/plan
POST /v1/generation-batches/g14/runs/{run_id}/start
POST /v1/generation-batches/g14/runs/{run_id}/pause
POST /v1/generation-batches/g14/runs/{run_id}/resume
POST /v1/generation-batches/g14/runs/{run_id}/cancel
GET  /v1/generation-batches/g14/runs/{run_id}/evidence
POST /v1/generation-batches/g14/runs/{run_id}/certify
```

## 10. CLI

```bash
frt batch g14 plan --project <project> --release <release>
frt batch g14 run --plan <plan>
frt batch g14 verify --run <run-id>
frt batch g14 certify --run <run-id> --level WM5
```

## 11. Verification

- Schema validation and compatibility tests.
- Unit and component tests for deterministic logic.
- API, event, data and permission contract tests.
- End-to-end positive, failure, cancellation, retry and recovery journeys.
- Mutation and adversarial tests for critical invariants.
- Evidence digest, lineage, certificate invalidation and reproducibility tests.

## 12. Release Gates

- [ ] 六条路径关键Journey通过
- [ ] 基础库和分包约束有效
- [ ] 支付/授权不得客户端自证成功
- [ ] setData和响应式语义保持
- [ ] 平台不支持能力显式降级

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
- A valid `WM5` or policy-approved lower certificate is issued for the exact scope.
