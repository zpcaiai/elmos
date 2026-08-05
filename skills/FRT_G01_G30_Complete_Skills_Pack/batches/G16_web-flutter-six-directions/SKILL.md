---
name: generation-batch-g16-web-flutter-six-directions
description: Web与Flutter双向六条转换路径，FRT G16实现级Batch规范。
version: 1.0.0
batch: G16
certificate: WF0-WF6
status: implementation-ready-specification
---

# Generation Batch G16：Web与Flutter双向六条转换路径

## 1. Mission

从：

> 三种Web框架和Flutter Widget/State模型

推进到：

> Vue2/Vue3/React与Flutter六条方向均可生成、构建和差分验证

本Batch必须产出可由Codex直接实施的Manifest、Schema、Runtime、API、CLI、管理端、测试、Evidence和Certificate，不允许仅停留在概念文档。

## 2. Core Capabilities

- 映射DOM/组件到Widget树而非逐元素复制
- 处理Key、BuildContext、Controller、State和Navigator
- 处理Plugin、Platform Channel、Web/Mobile能力差异

## 3. Inputs

- G1–G12、Flutter/Web Profiles和多端设备Fixture

## 4. Outputs

- 六个Web↔Flutter Packs
- Widget/State/Navigation Plans
- Plugin Gap Register
- Route Certificates

## 5. Global Hard Rules

- Source repository is read-only; generation, build, tests, mutation and repair run in isolated worktrees or sandboxes.
- Models propose candidates only; compilers, type checkers, formal kernels, independent tests and runtime evidence decide acceptance.
- No silent semantic loss, fake success, empty catch, fixed return, disabled assertion or UI-only authorization is permitted.
- All R4/R5 gates are non-compensatory; a critical failure cannot be hidden by aggregate scores.
- Every authoritative output binds input digests, toolchain, policy, environment, execution and evidence lineage.
- Unknown semantics must stop, emit a typed gap, request a product decision or escalate to a human reviewer.

## 6. Skills

- **FRT-1600 — Web Flutter Route Orchestrator** — [`skills/frt-1600-web-flutter-route-orchestrator/SKILL.md`](../../skills/frt-1600-web-flutter-route-orchestrator/SKILL.md)
- **FRT-1601 — Vue 2 to Flutter Route Pack** — [`skills/frt-1601-vue-2-to-flutter-route-pack/SKILL.md`](../../skills/frt-1601-vue-2-to-flutter-route-pack/SKILL.md)
- **FRT-1602 — Flutter to Vue 2 Route Pack** — [`skills/frt-1602-flutter-to-vue-2-route-pack/SKILL.md`](../../skills/frt-1602-flutter-to-vue-2-route-pack/SKILL.md)
- **FRT-1603 — Vue 3 to Flutter Route Pack** — [`skills/frt-1603-vue-3-to-flutter-route-pack/SKILL.md`](../../skills/frt-1603-vue-3-to-flutter-route-pack/SKILL.md)
- **FRT-1604 — Flutter to Vue 3 Route Pack** — [`skills/frt-1604-flutter-to-vue-3-route-pack/SKILL.md`](../../skills/frt-1604-flutter-to-vue-3-route-pack/SKILL.md)
- **FRT-1605 — React to Flutter Route Pack** — [`skills/frt-1605-react-to-flutter-route-pack/SKILL.md`](../../skills/frt-1605-react-to-flutter-route-pack/SKILL.md)
- **FRT-1606 — Flutter to React Route Pack** — [`skills/frt-1606-flutter-to-react-route-pack/SKILL.md`](../../skills/frt-1606-flutter-to-react-route-pack/SKILL.md)
- **FRT-1607 — Flutter Capability Gap Planner** — [`skills/frt-1607-flutter-capability-gap-planner/SKILL.md`](../../skills/frt-1607-flutter-capability-gap-planner/SKILL.md)
- **FRT-1608 — Flutter Widget State and Navigation Mapper** — [`skills/frt-1608-flutter-widget-state-and-navigation-mapper/SKILL.md`](../../skills/frt-1608-flutter-widget-state-and-navigation-mapper/SKILL.md)
- **FRT-1609 — Flutter Plugin and Platform Channel Mapper** — [`skills/frt-1609-flutter-plugin-and-platform-channel-mapper/SKILL.md`](../../skills/frt-1609-flutter-plugin-and-platform-channel-mapper/SKILL.md)
- **FRT-1610 — Web Flutter Differential Corpus** — [`skills/frt-1610-web-flutter-differential-corpus/SKILL.md`](../../skills/frt-1610-web-flutter-differential-corpus/SKILL.md)
- **FRT-1611 — Web Flutter Route Certification** — [`skills/frt-1611-web-flutter-route-certification/SKILL.md`](../../skills/frt-1611-web-flutter-route-certification/SKILL.md)

## 7. Orchestration Workflow

1. Validate prerequisite batch certificates, versions, digests and compatibility contracts.
2. Resolve the exact project, tenant, workspace, source snapshot, target profile, packs, policy and environment.
3. Compile batch-specific typed contracts and obligations before changing code or state.
4. Execute deterministic and independently verifiable steps first.
5. Use restricted agent proposals only for bounded unresolved work; never permit direct certification.
6. Run positive, negative, adversarial, mutation and recovery verification appropriate to risk.
7. Store all artifacts and findings in the evidence graph with immutable digests.
8. Stop on any R4/R5 blocker and create an actionable escalation packet.
9. Issue the G16 certificate only when every mandatory gate passes.

## 8. Common Implementation Surfaces

```text
packages/contracts/g16/
packages/runtime/g16/
services/control-plane/g16/
services/workers/g16/
apps/web-console/src/features/g16/
apps/admin-console/src/features/g16/
tests/g16/
evidence/g16/
```

## 9. Batch API

```text
POST /v1/generation-batches/g16/runs
GET  /v1/generation-batches/g16/runs/{run_id}
POST /v1/generation-batches/g16/runs/{run_id}/plan
POST /v1/generation-batches/g16/runs/{run_id}/start
POST /v1/generation-batches/g16/runs/{run_id}/pause
POST /v1/generation-batches/g16/runs/{run_id}/resume
POST /v1/generation-batches/g16/runs/{run_id}/cancel
GET  /v1/generation-batches/g16/runs/{run_id}/evidence
POST /v1/generation-batches/g16/runs/{run_id}/certify
```

## 10. CLI

```bash
frt batch g16 plan --project <project> --release <release>
frt batch g16 run --plan <plan>
frt batch g16 verify --run <run-id>
frt batch g16 certify --run <run-id> --level WF5
```

## 11. Verification

- Schema validation and compatibility tests.
- Unit and component tests for deterministic logic.
- API, event, data and permission contract tests.
- End-to-end positive, failure, cancellation, retry and recovery journeys.
- Mutation and adversarial tests for critical invariants.
- Evidence digest, lineage, certificate invalidation and reproducibility tests.

## 12. Release Gates

- [ ] 六条路径Analyzer/Test/Build通过
- [ ] Widget Identity和Controller Dispose正确
- [ ] DOM惯用法不泄漏到Flutter
- [ ] Plugin权限和Fallback明确
- [ ] Web/Mobile差异有Known Difference

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
- A valid `WF5` or policy-approved lower certificate is issued for the exact scope.
