---
name: government-service-public-interest-evaluation
description: "Execute authoritative Batch 17 Skill 645 for government service public interest evaluation. Use when Codex must design, operate, review, or verify this Vertical Solution Factory capability."
---

# Government Service Public Interest Evaluation

## Operating contract

Apply authoritative Batch 17 Skill 645. Read [the shared Batch 17 evidence boundary](../references/batch-17-vertical-solution-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `V17-G` from local implementation evidence.

## Authoritative specification

## Cases

```text
身份错误
代理申请
弱势用户
无障碍
多语言
申诉
记录公开
隐私删除请求
大规模申报
灾难期间服务
```

## Critical Gate

* 错误权益决定为0；
  -未授权数据访问为0；
  -公共记录丢失为0；
  -无障碍Critical缺陷为0；
  -申诉路径完整。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
