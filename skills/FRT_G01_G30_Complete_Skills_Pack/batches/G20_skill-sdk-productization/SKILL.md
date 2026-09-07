---
name: generation-batch-g20-skill-sdk-productization
description: Skill SDK、Runtime、Registry、Marketplace、Worker与一键产品化，FRT G20实现级Batch规范。
version: 1.0.0
batch: G20
certificate: PD0-PD6
status: implementation-ready-specification
---

# Generation Batch G20：Skill SDK、Runtime、Registry、Marketplace、Worker与一键产品化

## 1. Mission

从：

> 完整转换、验证和证明能力集合

推进到：

> 形成CLI/API/IDE/Web、分布式Worker、企业部署和一键迁移交付产品

本Batch必须产出可由Codex直接实施的Manifest、Schema、Runtime、API、CLI、管理端、测试、Evidence和Certificate，不允许仅停留在概念文档。

## 2. Core Capabilities

- 提供Skill SDK、Runtime、Registry和Marketplace
- 实现CLI、API、IDE、Web Console和Multi-Tenant Workspace
- Durable Workflow与分布式Worker支持暂停、恢复、取消和幂等
- Model Router、成本、Artifact/Evidence、Approval/RBAC/Audit
- 支持K8s、单机、私有化、Air-Gapped和一键迁移/验证/交付

## 3. Inputs

- G1–G19全部Skills、Packs、Schemas、Tests、Proof和Certificates

## 4. Outputs

- Product Runtime
- CLI/API/IDE/Web Console
- Worker Platform
- Registry/Marketplace
- Enterprise Deployment
- One-Click Workflows
- Productization Certificate

## 5. Global Hard Rules

- Source repository is read-only; generation, build, tests, mutation and repair run in isolated worktrees or sandboxes.
- Models propose candidates only; compilers, type checkers, formal kernels, independent tests and runtime evidence decide acceptance.
- No silent semantic loss, fake success, empty catch, fixed return, disabled assertion or UI-only authorization is permitted.
- All R4/R5 gates are non-compensatory; a critical failure cannot be hidden by aggregate scores.
- Every authoritative output binds input digests, toolchain, policy, environment, execution and evidence lineage.
- Unknown semantics must stop, emit a typed gap, request a product decision or escalate to a human reviewer.

## 6. Skills

- **FRT-2000 — Productization Orchestrator** — [`skills/frt-2000-productization-orchestrator/SKILL.md`](../../skills/frt-2000-productization-orchestrator/SKILL.md)
- **FRT-2001 — Skill SDK** — [`skills/frt-2001-skill-sdk/SKILL.md`](../../skills/frt-2001-skill-sdk/SKILL.md)
- **FRT-2002 — Skill Runtime** — [`skills/frt-2002-skill-runtime/SKILL.md`](../../skills/frt-2002-skill-runtime/SKILL.md)
- **FRT-2003 — Skill Registry** — [`skills/frt-2003-skill-registry/SKILL.md`](../../skills/frt-2003-skill-registry/SKILL.md)
- **FRT-2004 — Pack Marketplace** — [`skills/frt-2004-pack-marketplace/SKILL.md`](../../skills/frt-2004-pack-marketplace/SKILL.md)
- **FRT-2005 — Signing Permission and Trust Framework** — [`skills/frt-2005-signing-permission-and-trust-framework/SKILL.md`](../../skills/frt-2005-signing-permission-and-trust-framework/SKILL.md)
- **FRT-2006 — FRT CLI** — [`skills/frt-2006-frt-cli/SKILL.md`](../../skills/frt-2006-frt-cli/SKILL.md)
- **FRT-2007 — FRT API** — [`skills/frt-2007-frt-api/SKILL.md`](../../skills/frt-2007-frt-api/SKILL.md)
- **FRT-2008 — IDE Integration** — [`skills/frt-2008-ide-integration/SKILL.md`](../../skills/frt-2008-ide-integration/SKILL.md)
- **FRT-2009 — Web Console** — [`skills/frt-2009-web-console/SKILL.md`](../../skills/frt-2009-web-console/SKILL.md)
- **FRT-2010 — Workspace Multi-Tenant Platform** — [`skills/frt-2010-workspace-multi-tenant-platform/SKILL.md`](../../skills/frt-2010-workspace-multi-tenant-platform/SKILL.md)
- **FRT-2011 — Durable Job Orchestration** — [`skills/frt-2011-durable-job-orchestration/SKILL.md`](../../skills/frt-2011-durable-job-orchestration/SKILL.md)
- **FRT-2012 — Distributed Worker Runtime** — [`skills/frt-2012-distributed-worker-runtime/SKILL.md`](../../skills/frt-2012-distributed-worker-runtime/SKILL.md)
- **FRT-2013 — Model Router and Cost Governor** — [`skills/frt-2013-model-router-and-cost-governor/SKILL.md`](../../skills/frt-2013-model-router-and-cost-governor/SKILL.md)
- **FRT-2014 — Artifact and Evidence Store** — [`skills/frt-2014-artifact-and-evidence-store/SKILL.md`](../../skills/frt-2014-artifact-and-evidence-store/SKILL.md)
- **FRT-2015 — Approval Policy RBAC and Audit** — [`skills/frt-2015-approval-policy-rbac-and-audit/SKILL.md`](../../skills/frt-2015-approval-policy-rbac-and-audit/SKILL.md)
- **FRT-2016 — Enterprise Deployment Pack** — [`skills/frt-2016-enterprise-deployment-pack/SKILL.md`](../../skills/frt-2016-enterprise-deployment-pack/SKILL.md)
- **FRT-2017 — Kubernetes Single-Node and Air-Gapped Deployment** — [`skills/frt-2017-kubernetes-single-node-and-air-gapped-deployment/SKILL.md`](../../skills/frt-2017-kubernetes-single-node-and-air-gapped-deployment/SKILL.md)
- **FRT-2018 — One-Click Migration** — [`skills/frt-2018-one-click-migration/SKILL.md`](../../skills/frt-2018-one-click-migration/SKILL.md)
- **FRT-2019 — One-Click Verification** — [`skills/frt-2019-one-click-verification/SKILL.md`](../../skills/frt-2019-one-click-verification/SKILL.md)
- **FRT-2020 — One-Click Delivery** — [`skills/frt-2020-one-click-delivery/SKILL.md`](../../skills/frt-2020-one-click-delivery/SKILL.md)
- **FRT-2021 — Billing SLO and Observability** — [`skills/frt-2021-billing-slo-and-observability/SKILL.md`](../../skills/frt-2021-billing-slo-and-observability/SKILL.md)
- **FRT-2022 — Security Red Team Harness** — [`skills/frt-2022-security-red-team-harness/SKILL.md`](../../skills/frt-2022-security-red-team-harness/SKILL.md)
- **FRT-2023 — Productization Certification** — [`skills/frt-2023-productization-certification/SKILL.md`](../../skills/frt-2023-productization-certification/SKILL.md)

## 7. Orchestration Workflow

1. Validate prerequisite batch certificates, versions, digests and compatibility contracts.
2. Resolve the exact project, tenant, workspace, source snapshot, target profile, packs, policy and environment.
3. Compile batch-specific typed contracts and obligations before changing code or state.
4. Execute deterministic and independently verifiable steps first.
5. Use restricted agent proposals only for bounded unresolved work; never permit direct certification.
6. Run positive, negative, adversarial, mutation and recovery verification appropriate to risk.
7. Store all artifacts and findings in the evidence graph with immutable digests.
8. Stop on any R4/R5 blocker and create an actionable escalation packet.
9. Issue the G20 certificate only when every mandatory gate passes.

## 8. Common Implementation Surfaces

```text
packages/contracts/g20/
packages/runtime/g20/
services/control-plane/g20/
services/workers/g20/
apps/web-console/src/features/g20/
apps/admin-console/src/features/g20/
tests/g20/
evidence/g20/
```

## 9. Batch API

```text
POST /v1/generation-batches/g20/runs
GET  /v1/generation-batches/g20/runs/{run_id}
POST /v1/generation-batches/g20/runs/{run_id}/plan
POST /v1/generation-batches/g20/runs/{run_id}/start
POST /v1/generation-batches/g20/runs/{run_id}/pause
POST /v1/generation-batches/g20/runs/{run_id}/resume
POST /v1/generation-batches/g20/runs/{run_id}/cancel
GET  /v1/generation-batches/g20/runs/{run_id}/evidence
POST /v1/generation-batches/g20/runs/{run_id}/certify
```

## 10. CLI

```bash
frt batch g20 plan --project <project> --release <release>
frt batch g20 run --plan <plan>
frt batch g20 verify --run <run-id>
frt batch g20 certify --run <run-id> --level PD5
```

## 11. Verification

- Schema validation and compatibility tests.
- Unit and component tests for deterministic logic.
- API, event, data and permission contract tests.
- End-to-end positive, failure, cancellation, retry and recovery journeys.
- Mutation and adversarial tests for critical invariants.
- Evidence digest, lineage, certificate invalidation and reproducibility tests.

## 12. Release Gates

- [ ] Skill安装升级卸载和版本兼容可用
- [ ] 多租户隔离和RBAC通过
- [ ] Job暂停恢复取消幂等
- [ ] Worker Lease和Artifact Authority正确
- [ ] Air-Gapped可安装验证
- [ ] 一键流程不绕过Approval和Certificate
- [ ] 产品化安全红队通过

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
- A valid `PD5` or policy-approved lower certificate is issued for the exact scope.
