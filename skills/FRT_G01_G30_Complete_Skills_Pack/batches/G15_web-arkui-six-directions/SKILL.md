---
name: generation-batch-g15-web-arkui-six-directions
description: Web与ArkUI双向六条转换路径，FRT G15实现级Batch规范。
version: 1.0.0
batch: G15
certificate: WA0-WA6
status: implementation-ready-specification
---

# Generation Batch G15：Web与ArkUI双向六条转换路径

## 1. Mission

从：

> 三种Web框架和ArkUI组件/状态模型

推进到：

> Vue2/Vue3/React与ArkUI六条方向均具备可执行Route Pack

本Batch必须产出可由Codex直接实施的Manifest、Schema、Runtime、API、CLI、管理端、测试、Evidence和Certificate，不允许仅停留在概念文档。

## 2. Core Capabilities

- 映射ArkUI状态装饰器、Builder、Navigation和生命周期
- 处理Web DOM能力与ArkUI Native/Device差异
- 生成真机/模拟器和Accessibility验证

## 3. Inputs

- G1–G12、ArkUI/Web Target Profiles和设备矩阵

## 4. Outputs

- 六个Web↔ArkUI Packs
- State/Navigation Mappings
- Device Reports
- Route Certificates

## 5. Global Hard Rules

- Source repository is read-only; generation, build, tests, mutation and repair run in isolated worktrees or sandboxes.
- Models propose candidates only; compilers, type checkers, formal kernels, independent tests and runtime evidence decide acceptance.
- No silent semantic loss, fake success, empty catch, fixed return, disabled assertion or UI-only authorization is permitted.
- All R4/R5 gates are non-compensatory; a critical failure cannot be hidden by aggregate scores.
- Every authoritative output binds input digests, toolchain, policy, environment, execution and evidence lineage.
- Unknown semantics must stop, emit a typed gap, request a product decision or escalate to a human reviewer.

## 6. Skills

- **FRT-1500 — Web ArkUI Route Orchestrator** — [`skills/frt-1500-web-arkui-route-orchestrator/SKILL.md`](../../skills/frt-1500-web-arkui-route-orchestrator/SKILL.md)
- **FRT-1501 — Vue 2 to ArkUI Route Pack** — [`skills/frt-1501-vue-2-to-arkui-route-pack/SKILL.md`](../../skills/frt-1501-vue-2-to-arkui-route-pack/SKILL.md)
- **FRT-1502 — ArkUI to Vue 2 Route Pack** — [`skills/frt-1502-arkui-to-vue-2-route-pack/SKILL.md`](../../skills/frt-1502-arkui-to-vue-2-route-pack/SKILL.md)
- **FRT-1503 — Vue 3 to ArkUI Route Pack** — [`skills/frt-1503-vue-3-to-arkui-route-pack/SKILL.md`](../../skills/frt-1503-vue-3-to-arkui-route-pack/SKILL.md)
- **FRT-1504 — ArkUI to Vue 3 Route Pack** — [`skills/frt-1504-arkui-to-vue-3-route-pack/SKILL.md`](../../skills/frt-1504-arkui-to-vue-3-route-pack/SKILL.md)
- **FRT-1505 — React to ArkUI Route Pack** — [`skills/frt-1505-react-to-arkui-route-pack/SKILL.md`](../../skills/frt-1505-react-to-arkui-route-pack/SKILL.md)
- **FRT-1506 — ArkUI to React Route Pack** — [`skills/frt-1506-arkui-to-react-route-pack/SKILL.md`](../../skills/frt-1506-arkui-to-react-route-pack/SKILL.md)
- **FRT-1507 — ArkUI Capability Gap Planner** — [`skills/frt-1507-arkui-capability-gap-planner/SKILL.md`](../../skills/frt-1507-arkui-capability-gap-planner/SKILL.md)
- **FRT-1508 — ArkUI State Navigation and Lifecycle Mapper** — [`skills/frt-1508-arkui-state-navigation-and-lifecycle-mapper/SKILL.md`](../../skills/frt-1508-arkui-state-navigation-and-lifecycle-mapper/SKILL.md)
- **FRT-1509 — ArkUI Native Capability Mapper** — [`skills/frt-1509-arkui-native-capability-mapper/SKILL.md`](../../skills/frt-1509-arkui-native-capability-mapper/SKILL.md)
- **FRT-1510 — Web ArkUI Device Differential Corpus** — [`skills/frt-1510-web-arkui-device-differential-corpus/SKILL.md`](../../skills/frt-1510-web-arkui-device-differential-corpus/SKILL.md)
- **FRT-1511 — Web ArkUI Route Certification** — [`skills/frt-1511-web-arkui-route-certification/SKILL.md`](../../skills/frt-1511-web-arkui-route-certification/SKILL.md)

## 7. Orchestration Workflow

1. Validate prerequisite batch certificates, versions, digests and compatibility contracts.
2. Resolve the exact project, tenant, workspace, source snapshot, target profile, packs, policy and environment.
3. Compile batch-specific typed contracts and obligations before changing code or state.
4. Execute deterministic and independently verifiable steps first.
5. Use restricted agent proposals only for bounded unresolved work; never permit direct certification.
6. Run positive, negative, adversarial, mutation and recovery verification appropriate to risk.
7. Store all artifacts and findings in the evidence graph with immutable digests.
8. Stop on any R4/R5 blocker and create an actionable escalation packet.
9. Issue the G15 certificate only when every mandatory gate passes.

## 8. Common Implementation Surfaces

```text
packages/contracts/g15/
packages/runtime/g15/
services/control-plane/g15/
services/workers/g15/
apps/web-console/src/features/g15/
apps/admin-console/src/features/g15/
tests/g15/
evidence/g15/
```

## 9. Batch API

```text
POST /v1/generation-batches/g15/runs
GET  /v1/generation-batches/g15/runs/{run_id}
POST /v1/generation-batches/g15/runs/{run_id}/plan
POST /v1/generation-batches/g15/runs/{run_id}/start
POST /v1/generation-batches/g15/runs/{run_id}/pause
POST /v1/generation-batches/g15/runs/{run_id}/resume
POST /v1/generation-batches/g15/runs/{run_id}/cancel
GET  /v1/generation-batches/g15/runs/{run_id}/evidence
POST /v1/generation-batches/g15/runs/{run_id}/certify
```

## 10. CLI

```bash
frt batch g15 plan --project <project> --release <release>
frt batch g15 run --plan <plan>
frt batch g15 verify --run <run-id>
frt batch g15 certify --run <run-id> --level WA5
```

## 11. Verification

- Schema validation and compatibility tests.
- Unit and component tests for deterministic logic.
- API, event, data and permission contract tests.
- End-to-end positive, failure, cancellation, retry and recovery journeys.
- Mutation and adversarial tests for critical invariants.
- Evidence digest, lineage, certificate invalidation and reproducibility tests.

## 12. Release Gates

- [ ] 六条路径Build和关键设备Journey通过
- [ ] ArkUI状态装饰器语义正确
- [ ] Web-only DOM能力显式Gap
- [ ] Native Permission和Lifecycle完整
- [ ] 真机/模拟器Evidence绑定版本

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
- A valid `WA5` or policy-approved lower certificate is issued for the exact scope.
