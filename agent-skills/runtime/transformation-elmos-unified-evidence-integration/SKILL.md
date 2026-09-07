---
name: transformation-elmos-unified-evidence-integration
description: "将战略、Portfolio、依赖、Stakeholder、采用、决策、Cutover、收益和健康映射到ELMOS统一Evidence。"
---

# Unified Transformation Integration

## Extension

{
  "scope": "TRANSFORMATION_EXECUTION",
  "engine": "ELMOS_TRANSFORMATION_EXECUTION",
  "engineExtension": {
    "schema": "elmos.transformation-execution-evidence.v1",
    "artifactRef": "..."
  }
}

## Evidence类型

TRANSFORMATION_ESTATE
STRATEGIC_ALIGNMENT
TRANSFORMATION_PORTFOLIO
TRANSFORMATION_GOVERNANCE
PORTFOLIO_DEPENDENCY
CHANGE_PORTFOLIO
CHANGE_SATURATION
STAKEHOLDER_GRAPH
CHANGE_IMPACT
COMMUNICATION
ADOPTION
READINESS
RESISTANCE
SPONSORSHIP
DECISION
ESCALATION
TRANSFORMATION_WAVE
BUSINESS_CUTOVER
HYPERCARE
BENEFIT_REALIZATION
TRANSFORMATION_HEALTH
TRANSFORMATION_CLOSURE

## Risk映射

TRANSFORMATION_WITHOUT_OUTCOME
→ STRATEGY_EXECUTION_RISK

PORTFOLIO_DEPENDENCY_BLOCKED
→ TRANSFORMATION_INTEGRATION_RISK

CHANGE_SATURATION_CRITICAL
→ ORGANIZATION_ABSORPTION_RISK

SPONSOR_INACTIVE
→ LEADERSHIP_RISK

ADOPTION_LOW
→ BENEFIT_REALIZATION_RISK

DECISION_OVERDUE
→ TRANSFORMATION_GOVERNANCE_RISK

BUSINESS_READINESS_FAILED
→ CUTOVER_RISK

BENEFIT_NOT_REALIZED
→ INVESTMENT_VALUE_RISK

## Checks

ELMOS / Strategic Alignment
ELMOS / Transformation Governance
ELMOS / Portfolio Dependencies
ELMOS / Change Saturation
ELMOS / Stakeholder Coverage
ELMOS / Change Impact
ELMOS / Sponsorship
ELMOS / Business Readiness
ELMOS / Adoption
ELMOS / Decision Latency
ELMOS / Benefit Realization
ELMOS / Transformation Health
ELMOS / Transformation Closure

## Composite Change Set

Transformation Execution Change Set
├── Transformation Portfolio
├── Governance Model
├── Dependency Plan
├── Change Portfolio
├── Stakeholder Plan
├── Impact Plan
├── Adoption Plan
├── Sponsor Plan
├── Decision Plan
├── Cutover Plan
├── Benefit Plan
└── Closure Plan

## Audit

必须审计：

- Transformation创建和停止；
- Strategic Alignment变化；
- Portfolio重排；
- Saturation Override；
- Stakeholder数据访问；
- Sponsor变化；
- Concern关闭；
- Decision；
- Readiness Override；
- Cutover批准；
- Benefit确认；
- Health状态Override；
- Transformation关闭。

## 验收标准

- Transformation关联全部ELMOS引擎；
- Strategic Outcome连接Investment和Delivery；
- Adoption连接Organization和Benefit；
- Decision和Override完整审计；
- Risk、Evidence和Portfolio统一；
- Evidence Pack支持受限离线验收。
