---
name: developer-platform-and-software-supply-chain-integration
description: "Execute authoritative Batch 18 Skill 686 for 整合Git、CI/CD、Artifact、Secrets、开发环境和安全扫描。. Use when Codex must design, operate, review, or verify this Group Integration Factory capability."
---

# Developer Platform And Software Supply Chain Integration

## Operating contract

Apply authoritative Batch 18 Skill 686. Read [the shared Batch 18 evidence boundary](../references/batch-18-group-integration-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `M18-H` from local implementation evidence.

## Authoritative specification

## Description

整合Git、CI/CD、Artifact、Secrets、开发环境和安全扫描。

## 平台能力

```text
Source Control
CI/CD
Artifact Registry
Package Registry
Secret Management
Developer Portal
Observability
Security Scanning
Environment Provisioning
```

## Hard Rules

* 仓库迁移需保留历史和权限；
* CI Secret不能跨法人复制；
* Package和Artifact需验证来源；
* 开发团队迁移分Wave；
* 旧Pipeline需有冻结和退出计划；
* 生产发布权限需重新认证；
* 供应链安全不能因速度降低。

## Acceptance Criteria

* 开发团队使用目标平台；
* Build和Release可重复；
* Artifact来源完整；
* Secret和权限安全；
* 旧平台使用率持续下降；
* 开发者生产力可衡量。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
