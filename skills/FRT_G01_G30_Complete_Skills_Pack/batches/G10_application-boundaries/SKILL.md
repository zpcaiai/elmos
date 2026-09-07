---
name: generation-batch-g10-application-boundaries
description: Routes、Forms、Network、Storage、Identity与Permissions边界，FRT G10实现级Batch规范。
version: 1.0.0
batch: G10
certificate: AB0-AB6
status: implementation-ready-specification
---

# Generation Batch G10：Routes、Forms、Network、Storage、Identity与Permissions边界

## 1. Mission

从：

> 组件与运行时语义

推进到：

> 形成完整应用导航、表单、API、存储、身份和权限边界

本Batch必须产出可由Codex直接实施的Manifest、Schema、Runtime、API、CLI、管理端、测试、Evidence和Certificate，不允许仅停留在概念文档。

## 2. Core Capabilities

- 保持Route、History、Guard和Deep Link语义
- 表单Validation、错误、草稿和提交幂等完整
- API、Event、Storage和Realtime边界显式
- 区分Platform Identity、Business Account、Tenant和Permission

## 3. Inputs

- G8/G9结果、API Contract、Identity/Permission Model

## 4. Outputs

- Route Graph
- Form Contracts
- Network/Storage Adapters
- Identity/Authorization Contracts
- Boundary E2E Tests
- Boundary Certificate

## 5. Global Hard Rules

- Source repository is read-only; generation, build, tests, mutation and repair run in isolated worktrees or sandboxes.
- Models propose candidates only; compilers, type checkers, formal kernels, independent tests and runtime evidence decide acceptance.
- No silent semantic loss, fake success, empty catch, fixed return, disabled assertion or UI-only authorization is permitted.
- All R4/R5 gates are non-compensatory; a critical failure cannot be hidden by aggregate scores.
- Every authoritative output binds input digests, toolchain, policy, environment, execution and evidence lineage.
- Unknown semantics must stop, emit a typed gap, request a product decision or escalate to a human reviewer.

## 6. Skills

- **FRT-1000 — Application Boundary Orchestrator** — [`skills/frt-1000-application-boundary-orchestrator/SKILL.md`](../../skills/frt-1000-application-boundary-orchestrator/SKILL.md)
- **FRT-1001 — Route Graph Generator** — [`skills/frt-1001-route-graph-generator/SKILL.md`](../../skills/frt-1001-route-graph-generator/SKILL.md)
- **FRT-1002 — Navigation and History Mapper** — [`skills/frt-1002-navigation-and-history-mapper/SKILL.md`](../../skills/frt-1002-navigation-and-history-mapper/SKILL.md)
- **FRT-1003 — Route Guard Mapper** — [`skills/frt-1003-route-guard-mapper/SKILL.md`](../../skills/frt-1003-route-guard-mapper/SKILL.md)
- **FRT-1004 — Form Model Generator** — [`skills/frt-1004-form-model-generator/SKILL.md`](../../skills/frt-1004-form-model-generator/SKILL.md)
- **FRT-1005 — Validation and Error Contract Mapper** — [`skills/frt-1005-validation-and-error-contract-mapper/SKILL.md`](../../skills/frt-1005-validation-and-error-contract-mapper/SKILL.md)
- **FRT-1006 — Network Client Generator** — [`skills/frt-1006-network-client-generator/SKILL.md`](../../skills/frt-1006-network-client-generator/SKILL.md)
- **FRT-1007 — API Contract Mapper** — [`skills/frt-1007-api-contract-mapper/SKILL.md`](../../skills/frt-1007-api-contract-mapper/SKILL.md)
- **FRT-1008 — Storage Adapter Generator** — [`skills/frt-1008-storage-adapter-generator/SKILL.md`](../../skills/frt-1008-storage-adapter-generator/SKILL.md)
- **FRT-1009 — Identity and Session Mapper** — [`skills/frt-1009-identity-and-session-mapper/SKILL.md`](../../skills/frt-1009-identity-and-session-mapper/SKILL.md)
- **FRT-1010 — Authorization and Tenant Scope Mapper** — [`skills/frt-1010-authorization-and-tenant-scope-mapper/SKILL.md`](../../skills/frt-1010-authorization-and-tenant-scope-mapper/SKILL.md)
- **FRT-1011 — Realtime Webhook and Subscription Mapper** — [`skills/frt-1011-realtime-webhook-and-subscription-mapper/SKILL.md`](../../skills/frt-1011-realtime-webhook-and-subscription-mapper/SKILL.md)
- **FRT-1012 — Permission and Capability Mapper** — [`skills/frt-1012-permission-and-capability-mapper/SKILL.md`](../../skills/frt-1012-permission-and-capability-mapper/SKILL.md)
- **FRT-1013 — Application Boundary Certification** — [`skills/frt-1013-application-boundary-certification/SKILL.md`](../../skills/frt-1013-application-boundary-certification/SKILL.md)

## 7. Orchestration Workflow

1. Validate prerequisite batch certificates, versions, digests and compatibility contracts.
2. Resolve the exact project, tenant, workspace, source snapshot, target profile, packs, policy and environment.
3. Compile batch-specific typed contracts and obligations before changing code or state.
4. Execute deterministic and independently verifiable steps first.
5. Use restricted agent proposals only for bounded unresolved work; never permit direct certification.
6. Run positive, negative, adversarial, mutation and recovery verification appropriate to risk.
7. Store all artifacts and findings in the evidence graph with immutable digests.
8. Stop on any R4/R5 blocker and create an actionable escalation packet.
9. Issue the G10 certificate only when every mandatory gate passes.

## 8. Common Implementation Surfaces

```text
packages/contracts/g10/
packages/runtime/g10/
services/control-plane/g10/
services/workers/g10/
apps/web-console/src/features/g10/
apps/admin-console/src/features/g10/
tests/g10/
evidence/g10/
```

## 9. Batch API

```text
POST /v1/generation-batches/g10/runs
GET  /v1/generation-batches/g10/runs/{run_id}
POST /v1/generation-batches/g10/runs/{run_id}/plan
POST /v1/generation-batches/g10/runs/{run_id}/start
POST /v1/generation-batches/g10/runs/{run_id}/pause
POST /v1/generation-batches/g10/runs/{run_id}/resume
POST /v1/generation-batches/g10/runs/{run_id}/cancel
GET  /v1/generation-batches/g10/runs/{run_id}/evidence
POST /v1/generation-batches/g10/runs/{run_id}/certify
```

## 10. CLI

```bash
frt batch g10 plan --project <project> --release <release>
frt batch g10 run --plan <plan>
frt batch g10 verify --run <run-id>
frt batch g10 certify --run <run-id> --level AB5
```

## 11. Verification

- Schema validation and compatibility tests.
- Unit and component tests for deterministic logic.
- API, event, data and permission contract tests.
- End-to-end positive, failure, cancellation, retry and recovery journeys.
- Mutation and adversarial tests for critical invariants.
- Evidence digest, lineage, certificate invalidation and reproducibility tests.

## 12. Release Gates

- [ ] 关键Route和Guard完整
- [ ] 表单失败不丢Critical输入
- [ ] API/Storage字段语义和Scope保持
- [ ] UI-only Authorization=0
- [ ] 账号切换清理旧请求/Store/Cache
- [ ] Realtime订阅跨Tenant泄漏=0

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
- A valid `AB5` or policy-approved lower certificate is issued for the exact scope.
