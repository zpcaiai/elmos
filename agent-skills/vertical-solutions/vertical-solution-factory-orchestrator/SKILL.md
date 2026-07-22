---
name: vertical-solution-factory-orchestrator
description: "Execute authoritative Batch 17 Skill 593 for 组织行业研究、领域模型、监管控制、Recipe、测试、产品打包和渠道复制。. Use when Codex must design, operate, review, or verify this Vertical Solution Factory capability."
---

# Vertical Solution Factory Orchestrator

## Operating contract

Apply authoritative Batch 17 Skill 593. Read [the shared Batch 17 evidence boundary](../references/batch-17-vertical-solution-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `V17-G` from local implementation evidence.

## Authoritative specification

## Description

组织行业研究、领域模型、监管控制、Recipe、测试、产品打包和渠道复制。

## Workflow

```text
行业选择
→ Segment细分
→ 领域专家访谈
→ 标准和监管盘点
→ 领域模型
→ 控制模型
→ Recipe开发
→ 评测语料
→ Reference Architecture
→ POC
→ Design Partner
→ 产品化
→ 伙伴认证
→ 区域复制
```

## Inputs

```yaml
vertical_factory:
  industry: healthcare
  target_segments:
    - hospital
    - health-platform

  initial_regions: []
  design_partners: []
  target_source_stacks: []
  target_architectures: []
```

## Hard Rules

* 行业版本必须有真实Design Partner；
* 不能只根据公开文章构建领域模型；
* 产品、工程、合规和行业专家共同负责；
* 监管控制必须有来源和适用范围；
* 行业包不得修改Shared Core私有行为；
* 客户定制不能自动进入公共行业包；
* 每个行业版本必须有明确商业Owner。

## Acceptance Criteria

* 行业版本有完整Roadmap；
* 领域、监管和技术工作流互相连接；
* Design Partner参与；
* 产品化和定制边界清楚；
* 行业资产可版本化；
* 交付和渠道可以复用。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
