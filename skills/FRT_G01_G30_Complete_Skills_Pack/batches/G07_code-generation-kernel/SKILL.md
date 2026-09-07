---
name: generation-batch-g07-code-generation-kernel
description: Code Generation Kernel、AST Emitter、Typed Hole与确定性修复，FRT G07实现级Batch规范。
version: 1.0.0
batch: G07
certificate: CG0-CG6
status: implementation-ready-specification
---

# Generation Batch G07：Code Generation Kernel、AST Emitter、Typed Hole与确定性修复

## 1. Mission

从：

> Target Architecture IR和Semantic IR

推进到：

> 生成可追踪、可增量、可构建且不静默丢语义的目标代码

本Batch必须产出可由Codex直接实施的Manifest、Schema、Runtime、API、CLI、管理端、测试、Evidence和Certificate，不允许仅停留在概念文档。

## 2. Core Capabilities

- Typed IR经规则Pass降低到目标原生AST
- Gap生成Typed Hole而非空实现
- Format/Analyze/Build驱动有界确定性修复
- Agent仅提交受限Patch且不得削弱测试和策略
- 保护人工区域并生成Source-Target Provenance

## 3. Inputs

- G6 Architecture IR、G5 Plan、G3 Semantic IR、Target Toolchain

## 4. Outputs

- Target Repository Candidate
- Source-Target Map
- Generation Diagnostics
- Agent Change Register
- Generation Certificate

## 5. Global Hard Rules

- Source repository is read-only; generation, build, tests, mutation and repair run in isolated worktrees or sandboxes.
- Models propose candidates only; compilers, type checkers, formal kernels, independent tests and runtime evidence decide acceptance.
- No silent semantic loss, fake success, empty catch, fixed return, disabled assertion or UI-only authorization is permitted.
- All R4/R5 gates are non-compensatory; a critical failure cannot be hidden by aggregate scores.
- Every authoritative output binds input digests, toolchain, policy, environment, execution and evidence lineage.
- Unknown semantics must stop, emit a typed gap, request a product decision or escalate to a human reviewer.

## 6. Skills

- **FRT-0700 — Code Generation Orchestrator** — [`skills/frt-0700-code-generation-orchestrator/SKILL.md`](../../skills/frt-0700-code-generation-orchestrator/SKILL.md)
- **FRT-0701 — Typed Semantic Lowering Engine** — [`skills/frt-0701-typed-semantic-lowering-engine/SKILL.md`](../../skills/frt-0701-typed-semantic-lowering-engine/SKILL.md)
- **FRT-0702 — Rule Registry and Pass Manager** — [`skills/frt-0702-rule-registry-and-pass-manager/SKILL.md`](../../skills/frt-0702-rule-registry-and-pass-manager/SKILL.md)
- **FRT-0703 — Target Native AST Emitter** — [`skills/frt-0703-target-native-ast-emitter/SKILL.md`](../../skills/frt-0703-target-native-ast-emitter/SKILL.md)
- **FRT-0704 — Template JSX and Widget Emitter** — [`skills/frt-0704-template-jsx-and-widget-emitter/SKILL.md`](../../skills/frt-0704-template-jsx-and-widget-emitter/SKILL.md)
- **FRT-0705 — Import and Dependency Resolver** — [`skills/frt-0705-import-and-dependency-resolver/SKILL.md`](../../skills/frt-0705-import-and-dependency-resolver/SKILL.md)
- **FRT-0706 — Deterministic Naming and File Allocation** — [`skills/frt-0706-deterministic-naming-and-file-allocation/SKILL.md`](../../skills/frt-0706-deterministic-naming-and-file-allocation/SKILL.md)
- **FRT-0707 — Typed Hole and Gap Emitter** — [`skills/frt-0707-typed-hole-and-gap-emitter/SKILL.md`](../../skills/frt-0707-typed-hole-and-gap-emitter/SKILL.md)
- **FRT-0708 — Formatter Linter and Analyzer Integration** — [`skills/frt-0708-formatter-linter-and-analyzer-integration/SKILL.md`](../../skills/frt-0708-formatter-linter-and-analyzer-integration/SKILL.md)
- **FRT-0709 — Build and Diagnostic Adapter** — [`skills/frt-0709-build-and-diagnostic-adapter/SKILL.md`](../../skills/frt-0709-build-and-diagnostic-adapter/SKILL.md)
- **FRT-0710 — Deterministic Repair Loop** — [`skills/frt-0710-deterministic-repair-loop/SKILL.md`](../../skills/frt-0710-deterministic-repair-loop/SKILL.md)
- **FRT-0711 — Restricted Agent Repair Envelope** — [`skills/frt-0711-restricted-agent-repair-envelope/SKILL.md`](../../skills/frt-0711-restricted-agent-repair-envelope/SKILL.md)
- **FRT-0712 — Incremental Regeneration and Three-Way Merge** — [`skills/frt-0712-incremental-regeneration-and-three-way-merge/SKILL.md`](../../skills/frt-0712-incremental-regeneration-and-three-way-merge/SKILL.md)
- **FRT-0713 — Source Target Map Generator** — [`skills/frt-0713-source-target-map-generator/SKILL.md`](../../skills/frt-0713-source-target-map-generator/SKILL.md)
- **FRT-0714 — Code Generation Certification** — [`skills/frt-0714-code-generation-certification/SKILL.md`](../../skills/frt-0714-code-generation-certification/SKILL.md)

## 7. Orchestration Workflow

1. Validate prerequisite batch certificates, versions, digests and compatibility contracts.
2. Resolve the exact project, tenant, workspace, source snapshot, target profile, packs, policy and environment.
3. Compile batch-specific typed contracts and obligations before changing code or state.
4. Execute deterministic and independently verifiable steps first.
5. Use restricted agent proposals only for bounded unresolved work; never permit direct certification.
6. Run positive, negative, adversarial, mutation and recovery verification appropriate to risk.
7. Store all artifacts and findings in the evidence graph with immutable digests.
8. Stop on any R4/R5 blocker and create an actionable escalation packet.
9. Issue the G07 certificate only when every mandatory gate passes.

## 8. Common Implementation Surfaces

```text
packages/contracts/g07/
packages/runtime/g07/
services/control-plane/g07/
services/workers/g07/
apps/web-console/src/features/g07/
apps/admin-console/src/features/g07/
tests/g07/
evidence/g07/
```

## 9. Batch API

```text
POST /v1/generation-batches/g07/runs
GET  /v1/generation-batches/g07/runs/{run_id}
POST /v1/generation-batches/g07/runs/{run_id}/plan
POST /v1/generation-batches/g07/runs/{run_id}/start
POST /v1/generation-batches/g07/runs/{run_id}/pause
POST /v1/generation-batches/g07/runs/{run_id}/resume
POST /v1/generation-batches/g07/runs/{run_id}/cancel
GET  /v1/generation-batches/g07/runs/{run_id}/evidence
POST /v1/generation-batches/g07/runs/{run_id}/certify
```

## 10. CLI

```bash
frt batch g07 plan --project <project> --release <release>
frt batch g07 run --plan <plan>
frt batch g07 verify --run <run-id>
frt batch g07 certify --run <run-id> --level CG5
```

## 11. Verification

- Schema validation and compatibility tests.
- Unit and component tests for deterministic logic.
- API, event, data and permission contract tests.
- End-to-end positive, failure, cancellation, retry and recovery journeys.
- Mutation and adversarial tests for critical invariants.
- Evidence digest, lineage, certificate invalidation and reproducibility tests.

## 12. Release Gates

- [ ] 禁止自由文本整仓生成
- [ ] 未知语义不得默认Any/空实现
- [ ] 目标代码可重新Parse、Typecheck、Build
- [ ] 相同输入产生确定性Digest
- [ ] Agent不得直接提交或修改Gate
- [ ] Source-Target Mapping覆盖达到策略

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
- A valid `CG5` or policy-approved lower certificate is issued for the exact scope.
