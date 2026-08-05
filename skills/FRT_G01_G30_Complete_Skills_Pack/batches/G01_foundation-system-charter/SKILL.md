---
name: generation-batch-g01-foundation-system-charter
description: 系统宪章、Monorepo、Skill标准、Artifact与Release Gate基础，FRT G01实现级Batch规范。
version: 1.0.0
batch: G01
certificate: FD0-FD6
status: implementation-ready-specification
---

# Generation Batch G01：系统宪章、Monorepo、Skill标准、Artifact与Release Gate基础

## 1. Mission

从：

> 项目愿景与功能设想

推进到：

> 具备统一宪章、仓库结构、Skill协议、证据模型、隔离环境和基础发布门禁

本Batch必须产出可由Codex直接实施的Manifest、Schema、Runtime、API、CLI、管理端、测试、Evidence和Certificate，不允许仅停留在概念文档。

## 2. Core Capabilities

- 定义系统不可妥协语义与风险等级
- 建立可扩展Monorepo与稳定模块边界
- 统一Skill Manifest、输入输出Schema、权限、版本与证据协议
- Source只读、目标Worktree、Sandbox和Artifact不可变
- 建立Golden、Fixture、Diagnostics和基础Gate

## 3. Inputs

- 产品目标、支持技术栈、风险边界和部署模式
- 源仓库只读原则、认证与证据要求

## 4. Outputs

- System Charter
- Monorepo Template
- Skill Standard
- Plugin Protocol
- Artifact/Provenance Schema
- Sandbox Policy
- Foundation Certificate

## 5. Global Hard Rules

- Source repository is read-only; generation, build, tests, mutation and repair run in isolated worktrees or sandboxes.
- Models propose candidates only; compilers, type checkers, formal kernels, independent tests and runtime evidence decide acceptance.
- No silent semantic loss, fake success, empty catch, fixed return, disabled assertion or UI-only authorization is permitted.
- All R4/R5 gates are non-compensatory; a critical failure cannot be hidden by aggregate scores.
- Every authoritative output binds input digests, toolchain, policy, environment, execution and evidence lineage.
- Unknown semantics must stop, emit a typed gap, request a product decision or escalate to a human reviewer.

## 6. Skills

- **FRT-0100 — Foundation Orchestrator** — [`skills/frt-0100-foundation-orchestrator/SKILL.md`](../../skills/frt-0100-foundation-orchestrator/SKILL.md)
- **FRT-0101 — System Charter and Non-Negotiable Invariants** — [`skills/frt-0101-system-charter-and-non-negotiable-invariants/SKILL.md`](../../skills/frt-0101-system-charter-and-non-negotiable-invariants/SKILL.md)
- **FRT-0102 — Monorepo Bootstrap and Module Boundaries** — [`skills/frt-0102-monorepo-bootstrap-and-module-boundaries/SKILL.md`](../../skills/frt-0102-monorepo-bootstrap-and-module-boundaries/SKILL.md)
- **FRT-0103 — Skill Specification Standard** — [`skills/frt-0103-skill-specification-standard/SKILL.md`](../../skills/frt-0103-skill-specification-standard/SKILL.md)
- **FRT-0104 — Plugin and Extension Protocol** — [`skills/frt-0104-plugin-and-extension-protocol/SKILL.md`](../../skills/frt-0104-plugin-and-extension-protocol/SKILL.md)
- **FRT-0105 — Skill Registry Foundation** — [`skills/frt-0105-skill-registry-foundation/SKILL.md`](../../skills/frt-0105-skill-registry-foundation/SKILL.md)
- **FRT-0106 — Artifact and Provenance Model** — [`skills/frt-0106-artifact-and-provenance-model/SKILL.md`](../../skills/frt-0106-artifact-and-provenance-model/SKILL.md)
- **FRT-0107 — Configuration and Versioning Foundation** — [`skills/frt-0107-configuration-and-versioning-foundation/SKILL.md`](../../skills/frt-0107-configuration-and-versioning-foundation/SKILL.md)
- **FRT-0108 — Sandbox and Worktree Isolation** — [`skills/frt-0108-sandbox-and-worktree-isolation/SKILL.md`](../../skills/frt-0108-sandbox-and-worktree-isolation/SKILL.md)
- **FRT-0109 — Fixture, Golden and Corpus Foundation** — [`skills/frt-0109-fixture-golden-and-corpus-foundation/SKILL.md`](../../skills/frt-0109-fixture-golden-and-corpus-foundation/SKILL.md)
- **FRT-0110 — Release Gate Foundation** — [`skills/frt-0110-release-gate-foundation/SKILL.md`](../../skills/frt-0110-release-gate-foundation/SKILL.md)
- **FRT-0111 — Safety Constitution and Trust Boundary** — [`skills/frt-0111-safety-constitution-and-trust-boundary/SKILL.md`](../../skills/frt-0111-safety-constitution-and-trust-boundary/SKILL.md)

## 7. Orchestration Workflow

1. Validate prerequisite batch certificates, versions, digests and compatibility contracts.
2. Resolve the exact project, tenant, workspace, source snapshot, target profile, packs, policy and environment.
3. Compile batch-specific typed contracts and obligations before changing code or state.
4. Execute deterministic and independently verifiable steps first.
5. Use restricted agent proposals only for bounded unresolved work; never permit direct certification.
6. Run positive, negative, adversarial, mutation and recovery verification appropriate to risk.
7. Store all artifacts and findings in the evidence graph with immutable digests.
8. Stop on any R4/R5 blocker and create an actionable escalation packet.
9. Issue the G01 certificate only when every mandatory gate passes.

## 8. Common Implementation Surfaces

```text
packages/contracts/g01/
packages/runtime/g01/
services/control-plane/g01/
services/workers/g01/
apps/web-console/src/features/g01/
apps/admin-console/src/features/g01/
tests/g01/
evidence/g01/
```

## 9. Batch API

```text
POST /v1/generation-batches/g01/runs
GET  /v1/generation-batches/g01/runs/{run_id}
POST /v1/generation-batches/g01/runs/{run_id}/plan
POST /v1/generation-batches/g01/runs/{run_id}/start
POST /v1/generation-batches/g01/runs/{run_id}/pause
POST /v1/generation-batches/g01/runs/{run_id}/resume
POST /v1/generation-batches/g01/runs/{run_id}/cancel
GET  /v1/generation-batches/g01/runs/{run_id}/evidence
POST /v1/generation-batches/g01/runs/{run_id}/certify
```

## 10. CLI

```bash
frt batch g01 plan --project <project> --release <release>
frt batch g01 run --plan <plan>
frt batch g01 verify --run <run-id>
frt batch g01 certify --run <run-id> --level FD5
```

## 11. Verification

- Schema validation and compatibility tests.
- Unit and component tests for deterministic logic.
- API, event, data and permission contract tests.
- End-to-end positive, failure, cancellation, retry and recovery journeys.
- Mutation and adversarial tests for critical invariants.
- Evidence digest, lineage, certificate invalidation and reproducibility tests.

## 12. Release Gates

- [ ] 系统宪章和禁止项已版本化
- [ ] 所有Skill均有Manifest、Schema、Workflow、Verification、Stop条件和DoD
- [ ] Source不可写且Sandbox默认无生产Secret
- [ ] Artifact有Digest与Lineage
- [ ] 基础Release Gate不可被模型自行绕过

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
- A valid `FD5` or policy-approved lower certificate is issued for the exact scope.
