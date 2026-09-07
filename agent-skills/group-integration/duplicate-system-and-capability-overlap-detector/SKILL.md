---
name: duplicate-system-and-capability-overlap-detector
description: "Execute authoritative Batch 18 Skill 677 for 识别承担相同或重叠业务能力的系统。. Use when Codex must design, operate, review, or verify this Group Integration Factory capability."
---

# Duplicate System And Capability Overlap Detector

## Operating contract

Apply authoritative Batch 18 Skill 677. Read [the shared Batch 18 evidence boundary](../references/batch-18-group-integration-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `M18-H` from local implementation evidence.

## Authoritative specification

## Description

识别承担相同或重叠业务能力的系统。

## Duplicate Score

```text
业务能力相似度
+ 用户重叠
+ 数据重叠
+ 地区重叠
+ 流程重叠
+ 集成重叠
+ 成本重叠
```

## 结果类型

```text
True Duplicate
Regional Variant
Regulatory Variant
Different Segment
Complementary
Temporary Duplicate
Unknown
```

## Hard Rules

* 名称相似不能直接判定重复；
* 不以技术栈相同判定重复；
* 地区和法规差异需保留；
* 真实使用数据进入判断；
* 业务Owner参与；
* 重复系统识别不等于立即退役；
* 判断需说明置信度。

## Acceptance Criteria

* 重复能力清单可查询；
* 真重复和合理变体分开；
* 成本机会可估算；
* 处置决策有事实依据；
* False Positive可纠正。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
