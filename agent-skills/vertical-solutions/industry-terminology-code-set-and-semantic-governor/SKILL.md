---
name: industry-terminology-code-set-and-semantic-governor
description: "Execute authoritative Batch 17 Skill 596 for 管理行业术语、枚举、Code Set、标识规则和语义版本。. Use when Codex must design, operate, review, or verify this Vertical Solution Factory capability."
---

# Industry Terminology Code Set And Semantic Governor

## Operating contract

Apply authoritative Batch 17 Skill 596. Read [the shared Batch 17 evidence boundary](../references/batch-17-vertical-solution-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `V17-G` from local implementation evidence.

## Authoritative specification

## Description

管理行业术语、枚举、Code Set、标识规则和语义版本。

## Term Record

```yaml
industry_term:
  term_id: finance.available-balance
  preferred_label: Available Balance
  aliases: []
  definition: string
  context: deposit-account
  owner: domain-council
```

## Code Set

包括：

* 状态；
  -业务类型；
  -分类；
  -错误码；
  -风险等级；
  -机构代码；
  -设备类型；
  -医疗Code；
  -网络服务代码。

## Hard Rules

* 同名术语不能静默合并；
* Code值和显示名称分开；
* 历史Code需有有效期；
* 地区翻译不改变Code；
* 未知Code需兼容策略；
* 客户私有Code与公共Code分开；
* 术语修改触发Recipe和测试影响分析。

## Acceptance Criteria

* 行业术语一致；
* Code迁移可验证；
* 多语言显示不改变业务语义；
* 未知值不造成数据丢失；
* 历史版本可读取；
* 文档、API和测试使用同一术语。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
