---
name: generation-batch-g18-pack-overlay-composition
description: Domain、Framework、UI、State、Router、Build、Version、Enterprise与Industry Packs，FRT G18实现级Batch规范。
version: 1.0.0
batch: G18
certificate: PK0-PK6
status: implementation-ready-specification
---

# Generation Batch G18：Domain、Framework、UI、State、Router、Build、Version、Enterprise与Industry Packs

## 1. Mission

从：

> 30条基础方向路径

推进到：

> 通过可组合、签名、版本化Overlay适配真实企业和行业项目

本Batch必须产出可由Codex直接实施的Manifest、Schema、Runtime、API、CLI、管理端、测试、Evidence和Certificate，不允许仅停留在概念文档。

## 2. Core Capabilities

- 将真实项目差异封装为可组合Overlay而非硬编码核心
- Pack声明Provides/Requires/Conflicts/Permissions/Versions
- 确定性解析优先级和冲突
- Enterprise/Industry Packs保留安全与数据边界

## 3. Inputs

- G13–G17 Route Packs、企业库/框架/行业要求

## 4. Outputs

- Pack SDK
- Dependency/Conflict Graph
- Resolved Pack Lock
- Conformance Tests
- Pack Composition Certificate

## 5. Global Hard Rules

- Source repository is read-only; generation, build, tests, mutation and repair run in isolated worktrees or sandboxes.
- Models propose candidates only; compilers, type checkers, formal kernels, independent tests and runtime evidence decide acceptance.
- No silent semantic loss, fake success, empty catch, fixed return, disabled assertion or UI-only authorization is permitted.
- All R4/R5 gates are non-compensatory; a critical failure cannot be hidden by aggregate scores.
- Every authoritative output binds input digests, toolchain, policy, environment, execution and evidence lineage.
- Unknown semantics must stop, emit a typed gap, request a product decision or escalate to a human reviewer.

## 6. Skills

- **FRT-1800 — Pack Composition Orchestrator** — [`skills/frt-1800-pack-composition-orchestrator/SKILL.md`](../../skills/frt-1800-pack-composition-orchestrator/SKILL.md)
- **FRT-1801 — Domain Pack Framework** — [`skills/frt-1801-domain-pack-framework/SKILL.md`](../../skills/frt-1801-domain-pack-framework/SKILL.md)
- **FRT-1802 — Framework Pack Framework** — [`skills/frt-1802-framework-pack-framework/SKILL.md`](../../skills/frt-1802-framework-pack-framework/SKILL.md)
- **FRT-1803 — UI Library Pack Framework** — [`skills/frt-1803-ui-library-pack-framework/SKILL.md`](../../skills/frt-1803-ui-library-pack-framework/SKILL.md)
- **FRT-1804 — State Management Pack Framework** — [`skills/frt-1804-state-management-pack-framework/SKILL.md`](../../skills/frt-1804-state-management-pack-framework/SKILL.md)
- **FRT-1805 — Router Pack Framework** — [`skills/frt-1805-router-pack-framework/SKILL.md`](../../skills/frt-1805-router-pack-framework/SKILL.md)
- **FRT-1806 — Build Tool Pack Framework** — [`skills/frt-1806-build-tool-pack-framework/SKILL.md`](../../skills/frt-1806-build-tool-pack-framework/SKILL.md)
- **FRT-1807 — Version Compatibility Pack** — [`skills/frt-1807-version-compatibility-pack/SKILL.md`](../../skills/frt-1807-version-compatibility-pack/SKILL.md)
- **FRT-1808 — Enterprise Pack Framework** — [`skills/frt-1808-enterprise-pack-framework/SKILL.md`](../../skills/frt-1808-enterprise-pack-framework/SKILL.md)
- **FRT-1809 — Industry Pack Framework** — [`skills/frt-1809-industry-pack-framework/SKILL.md`](../../skills/frt-1809-industry-pack-framework/SKILL.md)
- **FRT-1810 — Pack Dependency Resolver** — [`skills/frt-1810-pack-dependency-resolver/SKILL.md`](../../skills/frt-1810-pack-dependency-resolver/SKILL.md)
- **FRT-1811 — Pack Conflict and Precedence Resolver** — [`skills/frt-1811-pack-conflict-and-precedence-resolver/SKILL.md`](../../skills/frt-1811-pack-conflict-and-precedence-resolver/SKILL.md)
- **FRT-1812 — Pack Signature and Permission Validator** — [`skills/frt-1812-pack-signature-and-permission-validator/SKILL.md`](../../skills/frt-1812-pack-signature-and-permission-validator/SKILL.md)
- **FRT-1813 — Pack Conformance Test Generator** — [`skills/frt-1813-pack-conformance-test-generator/SKILL.md`](../../skills/frt-1813-pack-conformance-test-generator/SKILL.md)
- **FRT-1814 — Pack Composition Certification** — [`skills/frt-1814-pack-composition-certification/SKILL.md`](../../skills/frt-1814-pack-composition-certification/SKILL.md)

## 7. Orchestration Workflow

1. Validate prerequisite batch certificates, versions, digests and compatibility contracts.
2. Resolve the exact project, tenant, workspace, source snapshot, target profile, packs, policy and environment.
3. Compile batch-specific typed contracts and obligations before changing code or state.
4. Execute deterministic and independently verifiable steps first.
5. Use restricted agent proposals only for bounded unresolved work; never permit direct certification.
6. Run positive, negative, adversarial, mutation and recovery verification appropriate to risk.
7. Store all artifacts and findings in the evidence graph with immutable digests.
8. Stop on any R4/R5 blocker and create an actionable escalation packet.
9. Issue the G18 certificate only when every mandatory gate passes.

## 8. Common Implementation Surfaces

```text
packages/contracts/g18/
packages/runtime/g18/
services/control-plane/g18/
services/workers/g18/
apps/web-console/src/features/g18/
apps/admin-console/src/features/g18/
tests/g18/
evidence/g18/
```

## 9. Batch API

```text
POST /v1/generation-batches/g18/runs
GET  /v1/generation-batches/g18/runs/{run_id}
POST /v1/generation-batches/g18/runs/{run_id}/plan
POST /v1/generation-batches/g18/runs/{run_id}/start
POST /v1/generation-batches/g18/runs/{run_id}/pause
POST /v1/generation-batches/g18/runs/{run_id}/resume
POST /v1/generation-batches/g18/runs/{run_id}/cancel
GET  /v1/generation-batches/g18/runs/{run_id}/evidence
POST /v1/generation-batches/g18/runs/{run_id}/certify
```

## 10. CLI

```bash
frt batch g18 plan --project <project> --release <release>
frt batch g18 run --plan <plan>
frt batch g18 verify --run <run-id>
frt batch g18 certify --run <run-id> --level PK5
```

## 11. Verification

- Schema validation and compatibility tests.
- Unit and component tests for deterministic logic.
- API, event, data and permission contract tests.
- End-to-end positive, failure, cancellation, retry and recovery journeys.
- Mutation and adversarial tests for critical invariants.
- Evidence digest, lineage, certificate invalidation and reproducibility tests.

## 12. Release Gates

- [ ] Pack组合确定性
- [ ] 未声明权限访问=0
- [ ] Conflict必须人工或规则解决
- [ ] 生产Pack必须签名和锁版本
- [ ] Pack撤销传播到受影响证书
- [ ] Conformance Corpus通过

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
- A valid `PK5` or policy-approved lower certificate is issued for the exact scope.
