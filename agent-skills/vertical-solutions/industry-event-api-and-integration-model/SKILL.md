---
name: industry-event-api-and-integration-model
description: "Execute authoritative Batch 17 Skill 603 for 定义行业API、事件、命令、消息和外部系统边界。. Use when Codex must design, operate, review, or verify this Vertical Solution Factory capability."
---

# Industry Event Api And Integration Model

## Operating contract

Apply authoritative Batch 17 Skill 603. Read [the shared Batch 17 evidence boundary](../references/batch-17-vertical-solution-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `V17-G` from local implementation evidence.

## Authoritative specification

## Description

定义行业API、事件、命令、消息和外部系统边界。

## Integration Record

```yaml
industry_integration:
  integration_id: finance-payment-clearing
  type: event
  schema_ref: string
  ordering: aggregate
  idempotency: required
  security: {}
  control_refs: []
```

## 必须描述

* 协议；
  -Schema；
  -Version；
  -身份；
  -顺序；
  -幂等；
  -重试；
  -DLQ；
  -时间；
  -数据分类；
  -审计；
  -兼容；
  -Owner。

## Hard Rules

* 行业标准消息不能只按JSON字段迁移；
* 业务Key和Correlation必须保留；
* 旧新Schema共存；
* 消息版本有消费者清单；
* External Integration有Contract Test；
* 敏感Payload受控；
* 无Owner接口不得产品化。

## Acceptance Criteria

* 行业集成边界完整；
* Schema兼容可验证；
* 消息副作用可比较；
* 外部调用证据可采集；
* Recipe可生成Adapter；
* Partner可获得标准接口包。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
