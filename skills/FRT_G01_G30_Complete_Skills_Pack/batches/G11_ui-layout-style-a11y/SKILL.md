---
name: generation-batch-g11-ui-layout-style-a11y
description: UI、Layout、Style、Assets、i18n与Accessibility语义，FRT G11实现级Batch规范。
version: 1.0.0
batch: G11
certificate: UI0-UI6
status: implementation-ready-specification
---

# Generation Batch G11：UI、Layout、Style、Assets、i18n与Accessibility语义

## 1. Mission

从：

> 源UI语义和目标组件

推进到：

> 保持视觉层级、响应式、资产、国际化和无障碍语义

本Batch必须产出可由Codex直接实施的Manifest、Schema、Runtime、API、CLI、管理端、测试、Evidence和Certificate，不允许仅停留在概念文档。

## 2. Core Capabilities

- 恢复布局约束、Design Token和响应式Size Class
- 生成资产、字体、Icon、Theme和动画映射
- 保持Locale、Plural、Date/Number和RTL语义
- 生成Web/Flutter/ArkUI/小程序Accessibility Contract

## 3. Inputs

- UI/Layout/Style IR、Design Assets、Locale Catalog、Target Platform Profile

## 4. Outputs

- Target UI System
- Asset/Theme/i18n Packages
- Accessibility Contracts
- Visual/Semantic Baselines
- UI Certificate

## 5. Global Hard Rules

- Source repository is read-only; generation, build, tests, mutation and repair run in isolated worktrees or sandboxes.
- Models propose candidates only; compilers, type checkers, formal kernels, independent tests and runtime evidence decide acceptance.
- No silent semantic loss, fake success, empty catch, fixed return, disabled assertion or UI-only authorization is permitted.
- All R4/R5 gates are non-compensatory; a critical failure cannot be hidden by aggregate scores.
- Every authoritative output binds input digests, toolchain, policy, environment, execution and evidence lineage.
- Unknown semantics must stop, emit a typed gap, request a product decision or escalate to a human reviewer.

## 6. Skills

- **FRT-1100 — UI Fidelity Orchestrator** — [`skills/frt-1100-ui-fidelity-orchestrator/SKILL.md`](../../skills/frt-1100-ui-fidelity-orchestrator/SKILL.md)
- **FRT-1101 — Layout Semantic Mapper** — [`skills/frt-1101-layout-semantic-mapper/SKILL.md`](../../skills/frt-1101-layout-semantic-mapper/SKILL.md)
- **FRT-1102 — Style and Design Token Mapper** — [`skills/frt-1102-style-and-design-token-mapper/SKILL.md`](../../skills/frt-1102-style-and-design-token-mapper/SKILL.md)
- **FRT-1103 — Responsive Layout Mapper** — [`skills/frt-1103-responsive-layout-mapper/SKILL.md`](../../skills/frt-1103-responsive-layout-mapper/SKILL.md)
- **FRT-1104 — Theme and Appearance Mapper** — [`skills/frt-1104-theme-and-appearance-mapper/SKILL.md`](../../skills/frt-1104-theme-and-appearance-mapper/SKILL.md)
- **FRT-1105 — Asset Pipeline Mapper** — [`skills/frt-1105-asset-pipeline-mapper/SKILL.md`](../../skills/frt-1105-asset-pipeline-mapper/SKILL.md)
- **FRT-1106 — Font Icon and Typography Mapper** — [`skills/frt-1106-font-icon-and-typography-mapper/SKILL.md`](../../skills/frt-1106-font-icon-and-typography-mapper/SKILL.md)
- **FRT-1107 — Internationalization Mapper** — [`skills/frt-1107-internationalization-mapper/SKILL.md`](../../skills/frt-1107-internationalization-mapper/SKILL.md)
- **FRT-1108 — RTL and Bidirectional Text Mapper** — [`skills/frt-1108-rtl-and-bidirectional-text-mapper/SKILL.md`](../../skills/frt-1108-rtl-and-bidirectional-text-mapper/SKILL.md)
- **FRT-1109 — Accessibility Semantic Mapper** — [`skills/frt-1109-accessibility-semantic-mapper/SKILL.md`](../../skills/frt-1109-accessibility-semantic-mapper/SKILL.md)
- **FRT-1110 — Animation and Transition Mapper** — [`skills/frt-1110-animation-and-transition-mapper/SKILL.md`](../../skills/frt-1110-animation-and-transition-mapper/SKILL.md)
- **FRT-1111 — Visual Regression Generator** — [`skills/frt-1111-visual-regression-generator/SKILL.md`](../../skills/frt-1111-visual-regression-generator/SKILL.md)
- **FRT-1112 — Semantic UI Regression Generator** — [`skills/frt-1112-semantic-ui-regression-generator/SKILL.md`](../../skills/frt-1112-semantic-ui-regression-generator/SKILL.md)
- **FRT-1113 — UI Fidelity Certification** — [`skills/frt-1113-ui-fidelity-certification/SKILL.md`](../../skills/frt-1113-ui-fidelity-certification/SKILL.md)

## 7. Orchestration Workflow

1. Validate prerequisite batch certificates, versions, digests and compatibility contracts.
2. Resolve the exact project, tenant, workspace, source snapshot, target profile, packs, policy and environment.
3. Compile batch-specific typed contracts and obligations before changing code or state.
4. Execute deterministic and independently verifiable steps first.
5. Use restricted agent proposals only for bounded unresolved work; never permit direct certification.
6. Run positive, negative, adversarial, mutation and recovery verification appropriate to risk.
7. Store all artifacts and findings in the evidence graph with immutable digests.
8. Stop on any R4/R5 blocker and create an actionable escalation packet.
9. Issue the G11 certificate only when every mandatory gate passes.

## 8. Common Implementation Surfaces

```text
packages/contracts/g11/
packages/runtime/g11/
services/control-plane/g11/
services/workers/g11/
apps/web-console/src/features/g11/
apps/admin-console/src/features/g11/
tests/g11/
evidence/g11/
```

## 9. Batch API

```text
POST /v1/generation-batches/g11/runs
GET  /v1/generation-batches/g11/runs/{run_id}
POST /v1/generation-batches/g11/runs/{run_id}/plan
POST /v1/generation-batches/g11/runs/{run_id}/start
POST /v1/generation-batches/g11/runs/{run_id}/pause
POST /v1/generation-batches/g11/runs/{run_id}/resume
POST /v1/generation-batches/g11/runs/{run_id}/cancel
GET  /v1/generation-batches/g11/runs/{run_id}/evidence
POST /v1/generation-batches/g11/runs/{run_id}/certify
```

## 10. CLI

```bash
frt batch g11 plan --project <project> --release <release>
frt batch g11 run --plan <plan>
frt batch g11 verify --run <run-id>
frt batch g11 certify --run <run-id> --level UI5
```

## 11. Verification

- Schema validation and compatibility tests.
- Unit and component tests for deterministic logic.
- API, event, data and permission contract tests.
- End-to-end positive, failure, cancellation, retry and recovery journeys.
- Mutation and adversarial tests for critical invariants.
- Evidence digest, lineage, certificate invalidation and reproducibility tests.

## 12. Release Gates

- [ ] 关键布局无裁剪和不可达动作
- [ ] Design Token未登记漂移=0
- [ ] Locale/RTL关键Journey通过
- [ ] Accessible Name/Role/Focus保持
- [ ] 视觉差异均分类和批准

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
- A valid `UI5` or policy-approved lower certificate is issued for the exact scope.
