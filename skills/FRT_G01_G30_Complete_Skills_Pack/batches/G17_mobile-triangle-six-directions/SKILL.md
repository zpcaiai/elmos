---
name: generation-batch-g17-mobile-triangle-six-directions
description: 小程序、ArkUI、Flutter Mobile Triangle六条有向路径与30路径收口，FRT G17实现级Batch规范。
version: 1.0.0
batch: G17
certificate: TR0-TR6
status: implementation-ready-specification
---

# Generation Batch G17：小程序、ArkUI、Flutter Mobile Triangle六条有向路径与30路径收口

## 1. Mission

从：

> 三类移动平台能力和前24条路径

推进到：

> 补齐六条移动方向并完成全部30条有向转换路径认证

本Batch必须产出可由Codex直接实施的Manifest、Schema、Runtime、API、CLI、管理端、测试、Evidence和Certificate，不允许仅停留在概念文档。

## 2. Core Capabilities

- 补齐小程序/ArkUI/Flutter六个方向
- 统一移动Navigation、Lifecycle、Permission、Storage和Native能力
- 验证直接与间接三角路径
- 完成6×5=30条路径Coverage Registry

## 3. Inputs

- G13–G16 Path Packs、三类移动Profile和设备矩阵

## 4. Outputs

- 六个Mobile Route Packs
- Device Matrix
- Triangle Equivalence Reports
- 30-Path Certificate

## 5. Global Hard Rules

- Source repository is read-only; generation, build, tests, mutation and repair run in isolated worktrees or sandboxes.
- Models propose candidates only; compilers, type checkers, formal kernels, independent tests and runtime evidence decide acceptance.
- No silent semantic loss, fake success, empty catch, fixed return, disabled assertion or UI-only authorization is permitted.
- All R4/R5 gates are non-compensatory; a critical failure cannot be hidden by aggregate scores.
- Every authoritative output binds input digests, toolchain, policy, environment, execution and evidence lineage.
- Unknown semantics must stop, emit a typed gap, request a product decision or escalate to a human reviewer.

## 6. Skills

- **FRT-1700 — Mobile Triangle Route Orchestrator** — [`skills/frt-1700-mobile-triangle-route-orchestrator/SKILL.md`](../../skills/frt-1700-mobile-triangle-route-orchestrator/SKILL.md)
- **FRT-1701 — Mini Program to ArkUI Route Pack** — [`skills/frt-1701-mini-program-to-arkui-route-pack/SKILL.md`](../../skills/frt-1701-mini-program-to-arkui-route-pack/SKILL.md)
- **FRT-1702 — ArkUI to Mini Program Route Pack** — [`skills/frt-1702-arkui-to-mini-program-route-pack/SKILL.md`](../../skills/frt-1702-arkui-to-mini-program-route-pack/SKILL.md)
- **FRT-1703 — Mini Program to Flutter Route Pack** — [`skills/frt-1703-mini-program-to-flutter-route-pack/SKILL.md`](../../skills/frt-1703-mini-program-to-flutter-route-pack/SKILL.md)
- **FRT-1704 — Flutter to Mini Program Route Pack** — [`skills/frt-1704-flutter-to-mini-program-route-pack/SKILL.md`](../../skills/frt-1704-flutter-to-mini-program-route-pack/SKILL.md)
- **FRT-1705 — ArkUI to Flutter Route Pack** — [`skills/frt-1705-arkui-to-flutter-route-pack/SKILL.md`](../../skills/frt-1705-arkui-to-flutter-route-pack/SKILL.md)
- **FRT-1706 — Flutter to ArkUI Route Pack** — [`skills/frt-1706-flutter-to-arkui-route-pack/SKILL.md`](../../skills/frt-1706-flutter-to-arkui-route-pack/SKILL.md)
- **FRT-1707 — Mobile Capability Normalizer** — [`skills/frt-1707-mobile-capability-normalizer/SKILL.md`](../../skills/frt-1707-mobile-capability-normalizer/SKILL.md)
- **FRT-1708 — Mobile Navigation and Lifecycle Mapper** — [`skills/frt-1708-mobile-navigation-and-lifecycle-mapper/SKILL.md`](../../skills/frt-1708-mobile-navigation-and-lifecycle-mapper/SKILL.md)
- **FRT-1709 — Native Bridge and Device Mapper** — [`skills/frt-1709-native-bridge-and-device-mapper/SKILL.md`](../../skills/frt-1709-native-bridge-and-device-mapper/SKILL.md)
- **FRT-1710 — Mobile Device Matrix Validator** — [`skills/frt-1710-mobile-device-matrix-validator/SKILL.md`](../../skills/frt-1710-mobile-device-matrix-validator/SKILL.md)
- **FRT-1711 — Triangle Path Equivalence Validator** — [`skills/frt-1711-triangle-path-equivalence-validator/SKILL.md`](../../skills/frt-1711-triangle-path-equivalence-validator/SKILL.md)
- **FRT-1712 — Thirty-Path Coverage Registry** — [`skills/frt-1712-thirty-path-coverage-registry/SKILL.md`](../../skills/frt-1712-thirty-path-coverage-registry/SKILL.md)
- **FRT-1713 — Thirty-Path Certification** — [`skills/frt-1713-thirty-path-certification/SKILL.md`](../../skills/frt-1713-thirty-path-certification/SKILL.md)

## 7. Orchestration Workflow

1. Validate prerequisite batch certificates, versions, digests and compatibility contracts.
2. Resolve the exact project, tenant, workspace, source snapshot, target profile, packs, policy and environment.
3. Compile batch-specific typed contracts and obligations before changing code or state.
4. Execute deterministic and independently verifiable steps first.
5. Use restricted agent proposals only for bounded unresolved work; never permit direct certification.
6. Run positive, negative, adversarial, mutation and recovery verification appropriate to risk.
7. Store all artifacts and findings in the evidence graph with immutable digests.
8. Stop on any R4/R5 blocker and create an actionable escalation packet.
9. Issue the G17 certificate only when every mandatory gate passes.

## 8. Common Implementation Surfaces

```text
packages/contracts/g17/
packages/runtime/g17/
services/control-plane/g17/
services/workers/g17/
apps/web-console/src/features/g17/
apps/admin-console/src/features/g17/
tests/g17/
evidence/g17/
```

## 9. Batch API

```text
POST /v1/generation-batches/g17/runs
GET  /v1/generation-batches/g17/runs/{run_id}
POST /v1/generation-batches/g17/runs/{run_id}/plan
POST /v1/generation-batches/g17/runs/{run_id}/start
POST /v1/generation-batches/g17/runs/{run_id}/pause
POST /v1/generation-batches/g17/runs/{run_id}/resume
POST /v1/generation-batches/g17/runs/{run_id}/cancel
GET  /v1/generation-batches/g17/runs/{run_id}/evidence
POST /v1/generation-batches/g17/runs/{run_id}/certify
```

## 10. CLI

```bash
frt batch g17 plan --project <project> --release <release>
frt batch g17 run --plan <plan>
frt batch g17 verify --run <run-id>
frt batch g17 certify --run <run-id> --level TR5
```

## 11. Verification

- Schema validation and compatibility tests.
- Unit and component tests for deterministic logic.
- API, event, data and permission contract tests.
- End-to-end positive, failure, cancellation, retry and recovery journeys.
- Mutation and adversarial tests for critical invariants.
- Evidence digest, lineage, certificate invalidation and reproducibility tests.

## 12. Release Gates

- [ ] 30条方向均有版本化Pack和Corpus
- [ ] 六条移动路径关键Journey通过
- [ ] 直接/间接路径Critical语义一致
- [ ] 设备能力和Unsupported状态完整
- [ ] 30路径无未披露Critical Gap

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
- A valid `TR5` or policy-approved lower certificate is issued for the exact scope.
