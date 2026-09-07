---
name: generation-batch-g12-platform-capabilities-native-bridges
description: 平台能力、Native Bridge、支付、权限与Device Fake，FRT G12实现级Batch规范。
version: 1.0.0
batch: G12
certificate: CP0-CP6
status: implementation-ready-specification
---

# Generation Batch G12：平台能力、Native Bridge、支付、权限与Device Fake

## 1. Mission

从：

> 框架中立平台Capability IR

推进到：

> 在各目标平台安全实现或明确降级原生能力

本Batch必须产出可由Codex直接实施的Manifest、Schema、Runtime、API、CLI、管理端、测试、Evidence和Certificate，不允许仅停留在概念文档。

## 2. Core Capabilities

- 建立跨平台Capability Registry与支持等级
- Native Bridge具备Schema、Permission、Timeout和Error Contract
- 支付、设备和危险能力使用Server Authority与安全状态机
- 提供Device Fake、Sandbox和Unsupported UX

## 3. Inputs

- Platform Capability IR、目标设备/Runtime/Profile和安全政策

## 4. Outputs

- Capability Adapters
- Native Bridges
- Permission State Machines
- Device Fakes
- Unsupported UX
- Platform Certificate

## 5. Global Hard Rules

- Source repository is read-only; generation, build, tests, mutation and repair run in isolated worktrees or sandboxes.
- Models propose candidates only; compilers, type checkers, formal kernels, independent tests and runtime evidence decide acceptance.
- No silent semantic loss, fake success, empty catch, fixed return, disabled assertion or UI-only authorization is permitted.
- All R4/R5 gates are non-compensatory; a critical failure cannot be hidden by aggregate scores.
- Every authoritative output binds input digests, toolchain, policy, environment, execution and evidence lineage.
- Unknown semantics must stop, emit a typed gap, request a product decision or escalate to a human reviewer.

## 6. Skills

- **FRT-1200 — Platform Capability Orchestrator** — [`skills/frt-1200-platform-capability-orchestrator/SKILL.md`](../../skills/frt-1200-platform-capability-orchestrator/SKILL.md)
- **FRT-1201 — Platform Capability Registry** — [`skills/frt-1201-platform-capability-registry/SKILL.md`](../../skills/frt-1201-platform-capability-registry/SKILL.md)
- **FRT-1202 — Native Bridge Generator** — [`skills/frt-1202-native-bridge-generator/SKILL.md`](../../skills/frt-1202-native-bridge-generator/SKILL.md)
- **FRT-1203 — File Clipboard and Share Capability** — [`skills/frt-1203-file-clipboard-and-share-capability/SKILL.md`](../../skills/frt-1203-file-clipboard-and-share-capability/SKILL.md)
- **FRT-1204 — Camera Media and Picker Capability** — [`skills/frt-1204-camera-media-and-picker-capability/SKILL.md`](../../skills/frt-1204-camera-media-and-picker-capability/SKILL.md)
- **FRT-1205 — Location Bluetooth and Device Capability** — [`skills/frt-1205-location-bluetooth-and-device-capability/SKILL.md`](../../skills/frt-1205-location-bluetooth-and-device-capability/SKILL.md)
- **FRT-1206 — Notification Capability** — [`skills/frt-1206-notification-capability/SKILL.md`](../../skills/frt-1206-notification-capability/SKILL.md)
- **FRT-1207 — Payment Capability** — [`skills/frt-1207-payment-capability/SKILL.md`](../../skills/frt-1207-payment-capability/SKILL.md)
- **FRT-1208 — Permission State Machine Generator** — [`skills/frt-1208-permission-state-machine-generator/SKILL.md`](../../skills/frt-1208-permission-state-machine-generator/SKILL.md)
- **FRT-1209 — App Lifecycle and Background Capability** — [`skills/frt-1209-app-lifecycle-and-background-capability/SKILL.md`](../../skills/frt-1209-app-lifecycle-and-background-capability/SKILL.md)
- **FRT-1210 — Device Fake and Simulator Generator** — [`skills/frt-1210-device-fake-and-simulator-generator/SKILL.md`](../../skills/frt-1210-device-fake-and-simulator-generator/SKILL.md)
- **FRT-1211 — Unsupported Capability UX Generator** — [`skills/frt-1211-unsupported-capability-ux-generator/SKILL.md`](../../skills/frt-1211-unsupported-capability-ux-generator/SKILL.md)
- **FRT-1212 — Platform Safety Validator** — [`skills/frt-1212-platform-safety-validator/SKILL.md`](../../skills/frt-1212-platform-safety-validator/SKILL.md)
- **FRT-1213 — Platform Capability Certification** — [`skills/frt-1213-platform-capability-certification/SKILL.md`](../../skills/frt-1213-platform-capability-certification/SKILL.md)

## 7. Orchestration Workflow

1. Validate prerequisite batch certificates, versions, digests and compatibility contracts.
2. Resolve the exact project, tenant, workspace, source snapshot, target profile, packs, policy and environment.
3. Compile batch-specific typed contracts and obligations before changing code or state.
4. Execute deterministic and independently verifiable steps first.
5. Use restricted agent proposals only for bounded unresolved work; never permit direct certification.
6. Run positive, negative, adversarial, mutation and recovery verification appropriate to risk.
7. Store all artifacts and findings in the evidence graph with immutable digests.
8. Stop on any R4/R5 blocker and create an actionable escalation packet.
9. Issue the G12 certificate only when every mandatory gate passes.

## 8. Common Implementation Surfaces

```text
packages/contracts/g12/
packages/runtime/g12/
services/control-plane/g12/
services/workers/g12/
apps/web-console/src/features/g12/
apps/admin-console/src/features/g12/
tests/g12/
evidence/g12/
```

## 9. Batch API

```text
POST /v1/generation-batches/g12/runs
GET  /v1/generation-batches/g12/runs/{run_id}
POST /v1/generation-batches/g12/runs/{run_id}/plan
POST /v1/generation-batches/g12/runs/{run_id}/start
POST /v1/generation-batches/g12/runs/{run_id}/pause
POST /v1/generation-batches/g12/runs/{run_id}/resume
POST /v1/generation-batches/g12/runs/{run_id}/cancel
GET  /v1/generation-batches/g12/runs/{run_id}/evidence
POST /v1/generation-batches/g12/runs/{run_id}/certify
```

## 10. CLI

```bash
frt batch g12 plan --project <project> --release <release>
frt batch g12 run --plan <plan>
frt batch g12 verify --run <run-id>
frt batch g12 certify --run <run-id> --level CP5
```

## 11. Verification

- Schema validation and compatibility tests.
- Unit and component tests for deterministic logic.
- API, event, data and permission contract tests.
- End-to-end positive, failure, cancellation, retry and recovery journeys.
- Mutation and adversarial tests for critical invariants.
- Evidence digest, lineage, certificate invalidation and reproducibility tests.

## 12. Release Gates

- [ ] Critical Capability不得Fake Success
- [ ] Payment最终状态由Server确认
- [ ] 危险设备命令Unknown不得盲目重试
- [ ] Permission状态完整
- [ ] Shadow/Fake不得产生Production副作用
- [ ] Unsupported能力有明确替代路径

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
- A valid `CP5` or policy-approved lower certificate is issued for the exact scope.
