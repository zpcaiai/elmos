---
name: clean-team-and-pre-close-data-boundary-manager
description: "Execute authoritative Batch 18 Skill 671 for 管理交割前Clean Team、敏感信息访问和分析边界。. Use when Codex must design, operate, review, or verify this Group Integration Factory capability."
---

# Clean Team And Pre Close Data Boundary Manager

## Operating contract

Apply authoritative Batch 18 Skill 671. Read [the shared Batch 18 evidence boundary](../references/batch-18-group-integration-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `M18-H` from local implementation evidence.

## Authoritative specification

## Description

管理交割前Clean Team、敏感信息访问和分析边界。

## 信息类别

```text
Public
Ordinary Confidential
Commercially Sensitive
Customer-specific
Pricing
Employee
Security
Source Code
Regulatory Restricted
```

## Clean Team Controls

* 指定人员；
  -独立Workspace；
  -最小数据；
  -脱敏；
  -输出审批；
  -访问期限；
  -下载限制；
  -不可向运营团队传递的内容；
  -销毁和归档。

## Hard Rules

* 交割前不得提前执行实际整合；
* 商业敏感信息访问由法务确定；
* Clean Team输出必须经过审查；
* 数据不能复制到普通项目空间；
* 源代码访问需单独授权；
* Access在交易终止或交割后按政策处理；
* 法律适用范围由专业顾问确认。

## Acceptance Criteria

* Clean Team成员清晰；
* 信息访问可审计；
* 输出不泄露受限细节；
* 交易前分析和交割后执行分开；
* 数据处理符合交易政策。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
