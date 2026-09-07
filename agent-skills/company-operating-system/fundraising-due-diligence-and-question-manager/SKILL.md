---
name: fundraising-due-diligence-and-question-manager
description: "Execute authoritative Batch 15 Skill 509 for 管理投资人尽调请求、问题、责任人和回答一致性。. Use when Codex must design, operate, review, or verify this Company Operating and Governance System capability."
---

# Fundraising Due Diligence And Question Manager

## Operating contract

Apply authoritative Batch 15 Skill 509. Read [the shared Batch 15 evidence boundary](../references/batch-15-company-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `C15-G` from local implementation evidence.

## Authoritative specification

## Description

管理投资人尽调请求、问题、责任人和回答一致性。

## Question Categories

```text
Market
Customers
Revenue
Product
Technology
Security
Competition
Team
Finance
Legal
IP
Risks
```

## Q&A Record

```yaml
due_diligence_question:
  question_id: string
  investor_id: string
  category: security
  owner: string
  response: string
  evidence_refs: []
  approved: true
```

## Hard Rules

* 同一问题回答需一致；
* 法律和财务回答需相关负责人批准；
* 不确定内容不能猜测；
* 敏感客户信息按权限提供；
* 承诺需进入公司记录；
* 重大披露需董事会知晓；
* Q&A结果需更新FAQ和材料。

## Acceptance Criteria

* 尽调响应及时；
* 回答有证据；
* 各投资人材料一致；
* 敏感信息安全；
* 重大风险正确披露；
* 重复问题可复用。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
