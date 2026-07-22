---
name: legacy-retirement-and-asset-cleanup
description: "Execute authoritative Batch 18 Skill 744 for legacy retirement and asset cleanup. Use when Codex must design, operate, review, or verify this Group Integration Factory capability."
---

# Legacy Retirement And Asset Cleanup

## Operating contract

Apply authoritative Batch 18 Skill 744. Read [the shared Batch 18 evidence boundary](../references/batch-18-group-integration-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `M18-H` from local implementation evidence.

## Authoritative specification

## Retirement对象

```text
Applications
Databases
Servers
Cloud Accounts
Licenses
Networks
Certificates
Service Accounts
Vendor Contracts
Monitoring
Backups
TSA
```

## Hard Rules

* 实际流量为0；
* 业务Owner确认；
* 数据归档和Restore验证；
* Credential撤销；
* 依赖扫描完成；
* Stranded Cost行动存在；
* CMDB和财务资产更新。

## Acceptance Criteria

* 旧系统不再承担业务责任；
* 数据和审计可恢复；
* 无隐藏调用方；
* 成本真正移除；
* 资产状态准确；
* TSA和合同正确结束。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
