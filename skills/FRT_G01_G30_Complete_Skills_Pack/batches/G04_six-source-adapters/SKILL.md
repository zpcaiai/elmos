---
name: generation-batch-g04-six-source-adapters
description: Vue2、Vue3、React、小程序、ArkUI、Flutter六类Source Adapter，FRT G04实现级Batch规范。
version: 1.0.0
batch: G04
certificate: SA0-SA6
status: implementation-ready-specification
---

# Generation Batch G04：Vue2、Vue3、React、小程序、ArkUI、Flutter六类Source Adapter

## 1. Mission

从：

> 六种框架的不同AST、模板和运行模型

推进到：

> 通过一致Adapter Contract生成同构Typed Semantic IR

本Batch必须产出可由Codex直接实施的Manifest、Schema、Runtime、API、CLI、管理端、测试、Evidence和Certificate，不允许仅停留在概念文档。

## 2. Core Capabilities

- 每个Adapter只解析源，不生成目标代码
- 恢复组件、状态、事件、生命周期、路由、样式和平台能力
- 统一动态语法、宏、装饰器和模板表达式
- 建立六框架Conformance Corpus

## 3. Inputs

- G2 Snapshot与G3 IR Schema

## 4. Outputs

- 六类Source Adapter
- Normalized Source Model
- Adapter Diagnostics
- Conformance Certificate

## 5. Global Hard Rules

- Source repository is read-only; generation, build, tests, mutation and repair run in isolated worktrees or sandboxes.
- Models propose candidates only; compilers, type checkers, formal kernels, independent tests and runtime evidence decide acceptance.
- No silent semantic loss, fake success, empty catch, fixed return, disabled assertion or UI-only authorization is permitted.
- All R4/R5 gates are non-compensatory; a critical failure cannot be hidden by aggregate scores.
- Every authoritative output binds input digests, toolchain, policy, environment, execution and evidence lineage.
- Unknown semantics must stop, emit a typed gap, request a product decision or escalate to a human reviewer.

## 6. Skills

- **FRT-0400 — Source Adapter Orchestrator** — [`skills/frt-0400-source-adapter-orchestrator/SKILL.md`](../../skills/frt-0400-source-adapter-orchestrator/SKILL.md)
- **FRT-0401 — Vue 2 Source Adapter** — [`skills/frt-0401-vue-2-source-adapter/SKILL.md`](../../skills/frt-0401-vue-2-source-adapter/SKILL.md)
- **FRT-0402 — Vue 3 Source Adapter** — [`skills/frt-0402-vue-3-source-adapter/SKILL.md`](../../skills/frt-0402-vue-3-source-adapter/SKILL.md)
- **FRT-0403 — React Source Adapter** — [`skills/frt-0403-react-source-adapter/SKILL.md`](../../skills/frt-0403-react-source-adapter/SKILL.md)
- **FRT-0404 — WeChat Mini Program Source Adapter** — [`skills/frt-0404-wechat-mini-program-source-adapter/SKILL.md`](../../skills/frt-0404-wechat-mini-program-source-adapter/SKILL.md)
- **FRT-0405 — ArkUI Source Adapter** — [`skills/frt-0405-arkui-source-adapter/SKILL.md`](../../skills/frt-0405-arkui-source-adapter/SKILL.md)
- **FRT-0406 — Flutter Source Adapter** — [`skills/frt-0406-flutter-source-adapter/SKILL.md`](../../skills/frt-0406-flutter-source-adapter/SKILL.md)
- **FRT-0407 — Source AST Normalizer** — [`skills/frt-0407-source-ast-normalizer/SKILL.md`](../../skills/frt-0407-source-ast-normalizer/SKILL.md)
- **FRT-0408 — Template JSX and Widget Extractor** — [`skills/frt-0408-template-jsx-and-widget-extractor/SKILL.md`](../../skills/frt-0408-template-jsx-and-widget-extractor/SKILL.md)
- **FRT-0409 — Reactive State Extractor** — [`skills/frt-0409-reactive-state-extractor/SKILL.md`](../../skills/frt-0409-reactive-state-extractor/SKILL.md)
- **FRT-0410 — Lifecycle and Effect Extractor** — [`skills/frt-0410-lifecycle-and-effect-extractor/SKILL.md`](../../skills/frt-0410-lifecycle-and-effect-extractor/SKILL.md)
- **FRT-0411 — Router Navigation and Capability Extractor** — [`skills/frt-0411-router-navigation-and-capability-extractor/SKILL.md`](../../skills/frt-0411-router-navigation-and-capability-extractor/SKILL.md)
- **FRT-0412 — Source Adapter Conformance Certification** — [`skills/frt-0412-source-adapter-conformance-certification/SKILL.md`](../../skills/frt-0412-source-adapter-conformance-certification/SKILL.md)

## 7. Orchestration Workflow

1. Validate prerequisite batch certificates, versions, digests and compatibility contracts.
2. Resolve the exact project, tenant, workspace, source snapshot, target profile, packs, policy and environment.
3. Compile batch-specific typed contracts and obligations before changing code or state.
4. Execute deterministic and independently verifiable steps first.
5. Use restricted agent proposals only for bounded unresolved work; never permit direct certification.
6. Run positive, negative, adversarial, mutation and recovery verification appropriate to risk.
7. Store all artifacts and findings in the evidence graph with immutable digests.
8. Stop on any R4/R5 blocker and create an actionable escalation packet.
9. Issue the G04 certificate only when every mandatory gate passes.

## 8. Common Implementation Surfaces

```text
packages/contracts/g04/
packages/runtime/g04/
services/control-plane/g04/
services/workers/g04/
apps/web-console/src/features/g04/
apps/admin-console/src/features/g04/
tests/g04/
evidence/g04/
```

## 9. Batch API

```text
POST /v1/generation-batches/g04/runs
GET  /v1/generation-batches/g04/runs/{run_id}
POST /v1/generation-batches/g04/runs/{run_id}/plan
POST /v1/generation-batches/g04/runs/{run_id}/start
POST /v1/generation-batches/g04/runs/{run_id}/pause
POST /v1/generation-batches/g04/runs/{run_id}/resume
POST /v1/generation-batches/g04/runs/{run_id}/cancel
GET  /v1/generation-batches/g04/runs/{run_id}/evidence
POST /v1/generation-batches/g04/runs/{run_id}/certify
```

## 10. CLI

```bash
frt batch g04 plan --project <project> --release <release>
frt batch g04 run --plan <plan>
frt batch g04 verify --run <run-id>
frt batch g04 certify --run <run-id> --level SA5
```

## 11. Verification

- Schema validation and compatibility tests.
- Unit and component tests for deterministic logic.
- API, event, data and permission contract tests.
- End-to-end positive, failure, cancellation, retry and recovery journeys.
- Mutation and adversarial tests for critical invariants.
- Evidence digest, lineage, certificate invalidation and reproducibility tests.

## 12. Release Gates

- [ ] Adapter不得调用Target Emitter
- [ ] 关键语义提取覆盖率达到策略
- [ ] 动态和未知行为进入Gap
- [ ] Source Range和Semantic ID完整
- [ ] 六类Adapter Corpus通过

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
- A valid `SA5` or policy-approved lower certificate is issued for the exact scope.
