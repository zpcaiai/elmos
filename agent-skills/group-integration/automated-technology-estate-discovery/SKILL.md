---
name: automated-technology-estate-discovery
description: "Execute authoritative Batch 18 Skill 675 for 自动扫描代码、运行时、云、数据库、网络、证书和工具链。. Use when Codex must design, operate, review, or verify this Group Integration Factory capability."
---

# Automated Technology Estate Discovery

## Operating contract

Apply authoritative Batch 18 Skill 675. Read [the shared Batch 18 evidence boundary](../references/batch-18-group-integration-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `M18-H` from local implementation evidence.

## Authoritative specification

## Description

自动扫描代码、运行时、云、数据库、网络、证书和工具链。

## 发现对象

```text
Repositories
Languages
Frameworks
Build Tools
Dependencies
Databases
Queues
APIs
Certificates
Cloud Services
Containers
Schedulers
Service Accounts
```

## Hard Rules

* 扫描遵守法人和地区边界；
* 不执行破坏性发现；
* 发现结果需标记置信度；
* 运行时事实优先于文档；
* Secret自动脱敏；
* 未知资产进入人工核实；
* 扫描器版本进入Provenance。

## Acceptance Criteria

* 技术栈分布可查询；
* 依赖和版本可见；
* 未登记接口被发现；
* 高风险EOL组件可识别；
* 结果支持迁移自动估算。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
