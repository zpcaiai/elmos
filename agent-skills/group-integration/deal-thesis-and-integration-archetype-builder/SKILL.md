---
name: deal-thesis-and-integration-archetype-builder
description: "Execute authoritative Batch 18 Skill 670 for 把交易投资逻辑转换为可执行整合模式。. Use when Codex must design, operate, review, or verify this Group Integration Factory capability."
---

# Deal Thesis And Integration Archetype Builder

## Operating contract

Apply authoritative Batch 18 Skill 670. Read [the shared Batch 18 evidence boundary](../references/batch-18-group-integration-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `M18-H` from local implementation evidence.

## Authoritative specification

## Description

把交易投资逻辑转换为可执行整合模式。

## Deal Thesis

可能包括：

```text
获得客户
获得产品
获得技术
获得人才
进入地区
降低成本
退出重复License
获得数据或渠道
整合供应链
```

## Integration Archetype

```yaml
integration_archetype:
  business_domain: commerce
  mode: best-of-both
  strategic_reason: string
  target_platform: string
  transition_period: string
```

## Hard Rules

* 不能默认由收购方系统取代被收购方；
* 应用选择需基于能力和战略；
* 不同业务域可采用不同整合模式；
* 交易假设需有可验证指标；
* 技术目标不能与交易逻辑冲突；
* 模式变化需管理层批准；
* 未明确交易逻辑的整合工作不得无限扩张。

## Acceptance Criteria

* 各业务域整合模式明确；
* 模式与交易价值一致；
* 资源和时限可估算；
* 整合优先级有依据；
* 非整合范围明确。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
