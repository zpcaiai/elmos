---
name: batch-14-growth-and-ecosystem-conformance-gate
description: "Execute authoritative Batch 14 Skill 460 for batch 14 growth and ecosystem conformance gate. Use when Codex must design, operate, review, or verify this growth and ecosystem capability."
---

# Batch 14 Growth And Ecosystem Conformance Gate

## Operating contract

Apply authoritative Batch 14 Skill 460. Read [the shared Batch 14 growth boundary](../references/batch-14-growth-evidence-boundary.md) before acting.

1. Pin the tenant, region, locale, persona, channel, campaign, source, consent state, product version, policy version, owner, and evidence window.
2. Confirm the required inputs and systems of record. Treat missing, stale, conflicting, cross-tenant, or unauthorized evidence as NOT_RUN, INCONCLUSIVE, or blocking.
3. Execute or evaluate the capability using the authoritative specification below. Keep product, content, community, Marketplace, localization, regional, security, privacy, quality, retention, and economics guardrails non-compensating.
4. Preserve failed and negative outcomes. Do not convert plans, drafts, simulations, generated artifacts, or repository tests into field success.
5. Record metric definitions, costs, quality signals, decisions, evidence references, stop conditions, and the next responsible owner.
6. Return the acceptance criteria as PASSED, FAILED, NOT_RUN, or INCONCLUSIVE; do not claim G14-G until Skill 460 passes with complete external evidence.

## Authoritative specification

## Description

综合产品增长、内容、开发者、社区、Marketplace和国际扩张结果，判断平台是否具备可持续规模化增长能力。

## 核心指标

```yaml id="6fv7fj"
product_growth:
  signup_to_repository_rate: number
  repository_to_assessment_rate: number
  assessment_to_migration_rate: number
  time_to_first_value: duration
  activated_retention: number

content:
  qualified_organic_growth: number
  content_to_assessment_rate: number
  technical_accuracy_gate: 1.00

developer:
  api_activation_rate: number
  sdk_adoption_rate: number
  documentation_success_rate: number

community:
  answered_question_rate: number
  verified_answer_rate: number
  community_deflection_rate: number
  critical_abuse_incidents: 0

marketplace:
  certified_asset_rate: number
  search_success_rate: number
  install_to_verified-use_rate: number
  critical_security_incidents: 0

international:
  localization_coverage: number
  regional_compliance_pass_rate: 1.00
  local_support_readiness: number

channels:
  partner-sourced-pipeline: number
  regional-playbook-reuse_rate: number

economics:
  channel_cac_visibility: 1.00
  growth_contribution_margin_visibility: 1.00
```

## Gate G14-A：产品激活可重复

```yaml id="8fj5v3"
self_service_signup: passed
repository_connection: passed
assessment_activation: passed
time_to_value_measurable: true
trial_cost_control: passed
security_guardrails: passed
```

## Gate G14-B：内容和开发者生态可信

```yaml id="ti31gg"
technical_content_review_coverage: 1.00
docs_core_journeys_complete: 1.00
sdk_core_journeys_tested: 1.00
sample_repositories_building: 1.00
developer_portal_available: true
```

## Gate G14-C：社区安全和知识闭环

```yaml id="6mvvku"
community_identity_isolation: passed
moderation_sla: passed
malicious_content_controls: passed
verified_knowledge_workflow: passed
private_customer_leakage: 0
```

## Gate G14-D：Marketplace可安全增长

```yaml id="k29j4k"
publisher_verification: passed
executable_asset_security_gate: 1.00
license_gate: 1.00
install_rollback: passed
fake_review_controls: passed
critical_asset_incidents: 0
```

## Gate G14-E：国际化和本地化就绪

```yaml id="uz58ou"
i18n_architecture: passed
critical_ui_localization: passed
security_and_billing_human_review: 1.00
regional_format_testing: passed
regional_compliance: passed
```

## Gate G14-F：区域渠道可复制

```yaml id="6n1jav"
regional_entry_assessment: complete
launch_playbook: approved
local_support: ready
regional_partner_quality_gates: enforced
regional_metrics: available
```

## Gate G14-G：增长规模化候选

```yaml id="si02do"
all_product_growth_gates: passed
all_content_developer_gates: passed
all_community_gates: passed
all_marketplace_gates: passed
all_localization_gates: passed
all_regional_channel_gates: passed
growth_economics_visible: true
critical_open_growth_risks: 0
```

## Blocking Conditions

* North Star只衡量虚荣指标；
* Trial产生不可控模型或Runner成本；
* 自助用户可以绕过安全政策；
* 内容夸大自动化率；
* 代码示例无法构建；
* 过期文档误导用户；
* Developer Portal泄露私有内容；
* 社区出现未处理源码泄漏；
* 恶意Recipe进入Marketplace；
* Marketplace资产License未知；
* Publisher可操纵评价；
* Prompt或源码跨Tenant缓存；
* 关键UI机器翻译直接上线；
* Security或Billing翻译未经人工Review；
* 数据驻留和区域产品承诺不一致；
* 地区销售承诺未支持功能；
* 地区伙伴降低质量门禁；
* 本地SLA无实际支持能力；
* CAC、Marketplace补贴或区域投入不可见；
* 高增长伴随严重负毛利；
* 品牌主张无证据；
* Critical增长风险无Owner。

## Final Result

```json id="i8o7k2"
{
  "growth_platform_version": "growth-ecosystem-v1",
  "gate": "G14-G",
  "status": "scalable-growth-ready",
  "supported_motions": [
    "product-led-growth",
    "content-led-growth",
    "developer-led-growth",
    "community-led-growth",
    "marketplace-led-growth",
    "partner-led-regional-expansion"
  ],
  "open_non_blocking_items": []
}
```

## Hard Rules

* 流量增长不能替代客户价值增长；
* 用户增长不能以安全和隐私为代价；
* Marketplace数量不能替代质量；
* 国际化不能等同界面翻译；
* 地区复制不能降低产品和交付门禁；
* 渠道增长必须显示CAC、毛利和Retention；
* 只有G14-G通过，平台才具备可持续规模化增长能力。

## Acceptance Criteria

* 产品能自助产生首个价值；
* 内容持续带来高质量用户；
* 开发者可通过API、CLI和SDK构建；
* 社区能够产生可信知识和贡献；
* Marketplace形成供需网络效应；
* 产品可在多语言和多地区可靠使用；
* 区域伙伴模型可复制；
* 增长可持续且经济性可衡量。

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, guardrail results, and external_operation_executed=false for any control-plane-only evaluation.

