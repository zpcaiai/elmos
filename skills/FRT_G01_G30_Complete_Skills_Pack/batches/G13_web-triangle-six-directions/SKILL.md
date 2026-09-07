---
name: generation-batch-g13-web-triangle-six-directions
description: Vue2、Vue3、React Web Triangle六条有向转换路径，FRT G13实现级Batch规范。
version: 1.0.0
batch: G13
certificate: WR0-WR6
status: implementation-ready-specification
---

# Generation Batch G13：Vue2、Vue3、React Web Triangle六条有向转换路径

## 1. Mission

从：

> 通用生成内核和三种Web框架能力

推进到：

> 六条Web方向均具备独立Route Pack、Corpus和证书

本Batch必须产出可由Codex直接实施的Manifest、Schema、Runtime、API、CLI、管理端、测试、Evidence和Certificate，不允许仅停留在概念文档。

## 2. Core Capabilities

- 六个方向独立声明版本、能力和Known Differences
- 处理Options/Composition/Hooks、Router、Store、SFC/JSX差异
- 建立直接路径与三角间接路径差分验证

## 3. Inputs

- G1–G12核心能力、Web源/目标Profiles和Golden Repositories

## 4. Outputs

- 六个Web Direction Packs
- Route Corpora
- Differential Reports
- Web Route Certificates

## 5. Global Hard Rules

- Source repository is read-only; generation, build, tests, mutation and repair run in isolated worktrees or sandboxes.
- Models propose candidates only; compilers, type checkers, formal kernels, independent tests and runtime evidence decide acceptance.
- No silent semantic loss, fake success, empty catch, fixed return, disabled assertion or UI-only authorization is permitted.
- All R4/R5 gates are non-compensatory; a critical failure cannot be hidden by aggregate scores.
- Every authoritative output binds input digests, toolchain, policy, environment, execution and evidence lineage.
- Unknown semantics must stop, emit a typed gap, request a product decision or escalate to a human reviewer.

## 6. Skills

- **FRT-1300 — Web Triangle Route Orchestrator** — [`skills/frt-1300-web-triangle-route-orchestrator/SKILL.md`](../../skills/frt-1300-web-triangle-route-orchestrator/SKILL.md)
- **FRT-1301 — Vue 2 to Vue 3 Route Pack** — [`skills/frt-1301-vue-2-to-vue-3-route-pack/SKILL.md`](../../skills/frt-1301-vue-2-to-vue-3-route-pack/SKILL.md)
- **FRT-1302 — Vue 3 to Vue 2 Route Pack** — [`skills/frt-1302-vue-3-to-vue-2-route-pack/SKILL.md`](../../skills/frt-1302-vue-3-to-vue-2-route-pack/SKILL.md)
- **FRT-1303 — Vue 2 to React Route Pack** — [`skills/frt-1303-vue-2-to-react-route-pack/SKILL.md`](../../skills/frt-1303-vue-2-to-react-route-pack/SKILL.md)
- **FRT-1304 — React to Vue 2 Route Pack** — [`skills/frt-1304-react-to-vue-2-route-pack/SKILL.md`](../../skills/frt-1304-react-to-vue-2-route-pack/SKILL.md)
- **FRT-1305 — Vue 3 to React Route Pack** — [`skills/frt-1305-vue-3-to-react-route-pack/SKILL.md`](../../skills/frt-1305-vue-3-to-react-route-pack/SKILL.md)
- **FRT-1306 — React to Vue 3 Route Pack** — [`skills/frt-1306-react-to-vue-3-route-pack/SKILL.md`](../../skills/frt-1306-react-to-vue-3-route-pack/SKILL.md)
- **FRT-1307 — Web Direction Pack Registry** — [`skills/frt-1307-web-direction-pack-registry/SKILL.md`](../../skills/frt-1307-web-direction-pack-registry/SKILL.md)
- **FRT-1308 — Web State Router and UI Mapping** — [`skills/frt-1308-web-state-router-and-ui-mapping/SKILL.md`](../../skills/frt-1308-web-state-router-and-ui-mapping/SKILL.md)
- **FRT-1309 — Web Differential Corpus** — [`skills/frt-1309-web-differential-corpus/SKILL.md`](../../skills/frt-1309-web-differential-corpus/SKILL.md)
- **FRT-1310 — Web Route Certification** — [`skills/frt-1310-web-route-certification/SKILL.md`](../../skills/frt-1310-web-route-certification/SKILL.md)

## 7. Orchestration Workflow

1. Validate prerequisite batch certificates, versions, digests and compatibility contracts.
2. Resolve the exact project, tenant, workspace, source snapshot, target profile, packs, policy and environment.
3. Compile batch-specific typed contracts and obligations before changing code or state.
4. Execute deterministic and independently verifiable steps first.
5. Use restricted agent proposals only for bounded unresolved work; never permit direct certification.
6. Run positive, negative, adversarial, mutation and recovery verification appropriate to risk.
7. Store all artifacts and findings in the evidence graph with immutable digests.
8. Stop on any R4/R5 blocker and create an actionable escalation packet.
9. Issue the G13 certificate only when every mandatory gate passes.

## 8. Common Implementation Surfaces

```text
packages/contracts/g13/
packages/runtime/g13/
services/control-plane/g13/
services/workers/g13/
apps/web-console/src/features/g13/
apps/admin-console/src/features/g13/
tests/g13/
evidence/g13/
```

## 9. Batch API

```text
POST /v1/generation-batches/g13/runs
GET  /v1/generation-batches/g13/runs/{run_id}
POST /v1/generation-batches/g13/runs/{run_id}/plan
POST /v1/generation-batches/g13/runs/{run_id}/start
POST /v1/generation-batches/g13/runs/{run_id}/pause
POST /v1/generation-batches/g13/runs/{run_id}/resume
POST /v1/generation-batches/g13/runs/{run_id}/cancel
GET  /v1/generation-batches/g13/runs/{run_id}/evidence
POST /v1/generation-batches/g13/runs/{run_id}/certify
```

## 10. CLI

```bash
frt batch g13 plan --project <project> --release <release>
frt batch g13 run --plan <plan>
frt batch g13 verify --run <run-id>
frt batch g13 certify --run <run-id> --level WR5
```

## 11. Verification

- Schema validation and compatibility tests.
- Unit and component tests for deterministic logic.
- API, event, data and permission contract tests.
- End-to-end positive, failure, cancellation, retry and recovery journeys.
- Mutation and adversarial tests for critical invariants.
- Evidence digest, lineage, certificate invalidation and reproducibility tests.

## 12. Release Gates

- [ ] 六条路径均可构建和运行
- [ ] 直接与间接路径关键行为一致
- [ ] Vue2降级限制显式
- [ ] Hooks/Watch/Computed语义不机械映射
- [ ] 每条Route有独立版本和证书

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
- A valid `WR5` or policy-approved lower certificate is issued for the exact scope.
