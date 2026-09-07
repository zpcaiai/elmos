---
name: industry-evaluation-golden-and-test-corpus
description: "Execute authoritative Batch 17 Skill 605 for 建立行业行为等价、合规、安全、韧性和边界测试语料。. Use when Codex must design, operate, review, or verify this Vertical Solution Factory capability."
---

# Industry Evaluation Golden And Test Corpus

## Operating contract

Apply authoritative Batch 17 Skill 605. Read [the shared Batch 17 evidence boundary](../references/batch-17-vertical-solution-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `V17-G` from local implementation evidence.

## Authoritative specification

## Description

建立行业行为等价、合规、安全、韧性和边界测试语料。

## Corpus Types

```text
Domain Invariant
Golden Transaction
Regulatory Control
Authorization
Data Privacy
Failure Injection
Historical Incident
Boundary Value
Performance
Safety
```

## Case Record

```yaml
industry_eval_case:
  case_id: finance-rounding-boundary
  industry: finance
  input: {}
  required_observations: []
  expected_invariants: []
  severity: critical
```

## Hard Rules

* 高风险行业不能只依赖单元测试；
* 真实案例必须脱敏；
* Historical Incident需转回归测试；
* Regulation Case需绑定Control；
* Golden需领域专家确认；
* 不允许使用客户数据训练公共语料；
* Corpus版本与VSP绑定。

## Acceptance Criteria

* 关键Invariant覆盖；
* 正常、异常和攻击路径完整；
* Source/Target可双运行；
* 事故语料可复现；
* 伙伴交付使用同一语料；
* 商业认证引用评测结果。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
