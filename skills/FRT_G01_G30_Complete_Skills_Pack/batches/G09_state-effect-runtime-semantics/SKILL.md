---
name: generation-batch-g09-state-effect-runtime-semantics
description: State、Effect、Lifecycle、Concurrency、Cancellation与Resource语义，FRT G09实现级Batch规范。
version: 1.0.0
batch: G09
certificate: RS0-RS6
status: implementation-ready-specification
---

# Generation Batch G09：State、Effect、Lifecycle、Concurrency、Cancellation与Resource语义

## 1. Mission

从：

> 源框架运行时语义

推进到：

> 目标系统保持状态Authority、Effect顺序、取消、资源释放和恢复语义

本Batch必须产出可由Codex直接实施的Manifest、Schema、Runtime、API、CLI、管理端、测试、Evidence和Certificate，不允许仅停留在概念文档。

## 2. Core Capabilities

- 区分Local、Server、Global、Persistent和Derived State
- 保持Effect触发、Cleanup、Lifecycle和Evaluation Order
- 传播Cancellation并防止Stale Result Commit
- 建模Retry、Idempotency、Hydration、Offline和Checkpoint

## 3. Inputs

- State/Effect IR、目标Runtime Profile和业务不变量

## 4. Outputs

- State Ownership Map
- Effect/Lifecycle Plan
- Cancellation/Retry Contracts
- Runtime Tests
- Runtime Certificate

## 5. Global Hard Rules

- Source repository is read-only; generation, build, tests, mutation and repair run in isolated worktrees or sandboxes.
- Models propose candidates only; compilers, type checkers, formal kernels, independent tests and runtime evidence decide acceptance.
- No silent semantic loss, fake success, empty catch, fixed return, disabled assertion or UI-only authorization is permitted.
- All R4/R5 gates are non-compensatory; a critical failure cannot be hidden by aggregate scores.
- Every authoritative output binds input digests, toolchain, policy, environment, execution and evidence lineage.
- Unknown semantics must stop, emit a typed gap, request a product decision or escalate to a human reviewer.

## 6. Skills

- **FRT-0900 — Runtime Semantics Orchestrator** — [`skills/frt-0900-runtime-semantics-orchestrator/SKILL.md`](../../skills/frt-0900-runtime-semantics-orchestrator/SKILL.md)
- **FRT-0901 — State Ownership Mapper** — [`skills/frt-0901-state-ownership-mapper/SKILL.md`](../../skills/frt-0901-state-ownership-mapper/SKILL.md)
- **FRT-0902 — Derived State and Memoization Mapper** — [`skills/frt-0902-derived-state-and-memoization-mapper/SKILL.md`](../../skills/frt-0902-derived-state-and-memoization-mapper/SKILL.md)
- **FRT-0903 — Effect Semantics Mapper** — [`skills/frt-0903-effect-semantics-mapper/SKILL.md`](../../skills/frt-0903-effect-semantics-mapper/SKILL.md)
- **FRT-0904 — Lifecycle Ordering Validator** — [`skills/frt-0904-lifecycle-ordering-validator/SKILL.md`](../../skills/frt-0904-lifecycle-ordering-validator/SKILL.md)
- **FRT-0905 — Async and Concurrency Mapper** — [`skills/frt-0905-async-and-concurrency-mapper/SKILL.md`](../../skills/frt-0905-async-and-concurrency-mapper/SKILL.md)
- **FRT-0906 — Cancellation Propagation Mapper** — [`skills/frt-0906-cancellation-propagation-mapper/SKILL.md`](../../skills/frt-0906-cancellation-propagation-mapper/SKILL.md)
- **FRT-0907 — Resource Ownership and Cleanup Mapper** — [`skills/frt-0907-resource-ownership-and-cleanup-mapper/SKILL.md`](../../skills/frt-0907-resource-ownership-and-cleanup-mapper/SKILL.md)
- **FRT-0908 — Retry Backoff and Idempotency Mapper** — [`skills/frt-0908-retry-backoff-and-idempotency-mapper/SKILL.md`](../../skills/frt-0908-retry-backoff-and-idempotency-mapper/SKILL.md)
- **FRT-0909 — Persistence and Hydration Mapper** — [`skills/frt-0909-persistence-and-hydration-mapper/SKILL.md`](../../skills/frt-0909-persistence-and-hydration-mapper/SKILL.md)
- **FRT-0910 — Offline Resume and Checkpoint Mapper** — [`skills/frt-0910-offline-resume-and-checkpoint-mapper/SKILL.md`](../../skills/frt-0910-offline-resume-and-checkpoint-mapper/SKILL.md)
- **FRT-0911 — Runtime Race Detector** — [`skills/frt-0911-runtime-race-detector/SKILL.md`](../../skills/frt-0911-runtime-race-detector/SKILL.md)
- **FRT-0912 — Runtime Semantics Test Generator** — [`skills/frt-0912-runtime-semantics-test-generator/SKILL.md`](../../skills/frt-0912-runtime-semantics-test-generator/SKILL.md)
- **FRT-0913 — Runtime Semantics Certification** — [`skills/frt-0913-runtime-semantics-certification/SKILL.md`](../../skills/frt-0913-runtime-semantics-certification/SKILL.md)

## 7. Orchestration Workflow

1. Validate prerequisite batch certificates, versions, digests and compatibility contracts.
2. Resolve the exact project, tenant, workspace, source snapshot, target profile, packs, policy and environment.
3. Compile batch-specific typed contracts and obligations before changing code or state.
4. Execute deterministic and independently verifiable steps first.
5. Use restricted agent proposals only for bounded unresolved work; never permit direct certification.
6. Run positive, negative, adversarial, mutation and recovery verification appropriate to risk.
7. Store all artifacts and findings in the evidence graph with immutable digests.
8. Stop on any R4/R5 blocker and create an actionable escalation packet.
9. Issue the G09 certificate only when every mandatory gate passes.

## 8. Common Implementation Surfaces

```text
packages/contracts/g09/
packages/runtime/g09/
services/control-plane/g09/
services/workers/g09/
apps/web-console/src/features/g09/
apps/admin-console/src/features/g09/
tests/g09/
evidence/g09/
```

## 9. Batch API

```text
POST /v1/generation-batches/g09/runs
GET  /v1/generation-batches/g09/runs/{run_id}
POST /v1/generation-batches/g09/runs/{run_id}/plan
POST /v1/generation-batches/g09/runs/{run_id}/start
POST /v1/generation-batches/g09/runs/{run_id}/pause
POST /v1/generation-batches/g09/runs/{run_id}/resume
POST /v1/generation-batches/g09/runs/{run_id}/cancel
GET  /v1/generation-batches/g09/runs/{run_id}/evidence
POST /v1/generation-batches/g09/runs/{run_id}/certify
```

## 10. CLI

```bash
frt batch g09 plan --project <project> --release <release>
frt batch g09 run --plan <plan>
frt batch g09 verify --run <run-id>
frt batch g09 certify --run <run-id> --level RS5
```

## 11. Verification

- Schema validation and compatibility tests.
- Unit and component tests for deterministic logic.
- API, event, data and permission contract tests.
- End-to-end positive, failure, cancellation, retry and recovery journeys.
- Mutation and adversarial tests for critical invariants.
- Evidence digest, lineage, certificate invalidation and reproducibility tests.

## 12. Release Gates

- [ ] State Authority明确
- [ ] Effect无重复或遗漏Critical副作用
- [ ] 取消后不得启动新副作用
- [ ] Timer/Subscription/Controller全部释放
- [ ] Hydration和Offline冲突有策略
- [ ] Critical Race=0

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
- A valid `RS5` or policy-approved lower certificate is issued for the exact scope.
