---
name: industry-data-classification-and-residency-manager
description: "Execute authoritative Batch 17 Skill 600 for 定义行业数据类型、敏感度、访问、驻留、保留和脱敏规则。. Use when Codex must design, operate, review, or verify this Vertical Solution Factory capability."
---

# Industry Data Classification And Residency Manager

## Operating contract

Apply authoritative Batch 17 Skill 600. Read [the shared Batch 17 evidence boundary](../references/batch-17-vertical-solution-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `V17-G` from local implementation evidence.

## Authoritative specification

## Description

定义行业数据类型、敏感度、访问、驻留、保留和脱敏规则。

## Classification Dimensions

```text
Business Criticality
Confidentiality
Integrity
Availability
Personal Data
Regulated Data
Safety Impact
Financial Impact
National Security
```

## Example

```yaml
industry_data_class:
  class_id: healthcare-clinical-record
  confidentiality: restricted
  integrity: critical
  availability: high
  residency: jurisdiction-bound
  model_access: restricted
```

## Hard Rules

* 行业标签不能替代字段级分类；
* Derived数据可能仍然敏感；
* 测试和Golden同样受分类；
* 模型Context遵守数据政策；
* 数据驻留覆盖处理和Backup；
* 删除和Legal Hold需结合行业要求；
* 跨行业客户数据不能错误共享。

## Acceptance Criteria

* 核心数据分类覆盖100%；
* 权限和Encryption与分类一致；
* 模型路由符合数据政策；
* Retention可自动执行；
* 脱敏保持业务引用；
* Data Flow可导出。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
