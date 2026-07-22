---
name: organization-workforce-elmos-unified-evidence-integration
description: "将组织、团队、岗位、技能、学习、AI增强、供应商、风险和变革结果映射到ELMOS统一Evidence。"
---

# Unified Organization Integration

## Extension

{
  "scope": "ORGANIZATION_WORKFORCE",
  "engine": "ELMOS_ORGANIZATION_WORKFORCE",
  "engineExtension": {
    "schema": "elmos.organization-workforce-evidence.v1",
    "artifactRef": "..."
  }
}

## Evidence类型

ORGANIZATION_ESTATE
PRODUCT_OPERATING_MODEL
TEAM_TOPOLOGY
TEAM_INTERACTION
COGNITIVE_LOAD
WORK_ARCHITECTURE
SKILL_ONTOLOGY
SKILL_EVIDENCE
TEAM_SKILL_COVERAGE
JOB_ARCHITECTURE
CAREER_FRAMEWORK
WORKFORCE_DEMAND
WORKFORCE_SUPPLY
AI_AUGMENTED_WORK
LEARNING_EFFECTIVENESS
CREDENTIAL
TALENT_MOBILITY
SUCCESSION
KEY_PERSON_RISK
VENDOR_WORKFORCE
TEAM_HEALTH
WORKFORCE_TRANSITION
ORGANIZATION_OUTCOME

## Risk映射

UNKNOWN_PRODUCT_OWNER
→ PRODUCT_ACCOUNTABILITY_RISK

TEAM_COGNITIVE_OVERLOAD
→ DELIVERY_SUSTAINABILITY_RISK

SKILL_COVERAGE_GAP
→ CAPABILITY_EXECUTION_RISK

KEY_PERSON_CONCENTRATION
→ KNOWLEDGE_CONTINUITY_RISK

VENDOR_KNOWLEDGE_LOCK_IN
→ SUPPLIER_CONTINUITY_RISK

AI_ACCOUNTABILITY_UNKNOWN
→ AI_WORKFORCE_GOVERNANCE_RISK

WORKFORCE_TRANSITION_UNFAIR
→ HUMAN_CAPITAL_RISK

ONCALL_OVERLOAD
→ WORKFORCE_WELLBEING_RISK

## Checks

ELMOS / Product Ownership
ELMOS / Team Mission
ELMOS / Team Cognitive Load
ELMOS / Skill Coverage
ELMOS / Career Framework
ELMOS / Workforce Capacity
ELMOS / AI Work Governance
ELMOS / Learning Effectiveness
ELMOS / Credential Validity
ELMOS / Key-person Risk
ELMOS / Vendor Continuity
ELMOS / Workforce Fairness
ELMOS / Organization Outcome

## Composite Change Set

Organization Modernization Change Set
├── Product Operating Model
├── Team Topology
├── Role Architecture
├── Skill Model
├── Career Framework
├── Workforce Plan
├── AI Work Design
├── Learning Plan
├── Succession Plan
├── Vendor Plan
└── Change Plan

## Audit

必须审计：

- Team Boundary变化；
- Product Owner变化；
- Role Requirement变化；
- Skill Evidence变化；
- Career Level变化；
- AI Task分配；
- Credential撤销；
- Talent Match；
- Succession决定；
- Key-person Risk访问；
- Vendor人员访问；
- High-impact Workforce Decision；
- Appeal；
- Organization Outcome确认。

## 验收标准

- 组织Evidence关联企业架构和产品；
- 技能需求关联现代化路线图；
- 人员数据采用独立安全边界；
- AI不能执行高影响人才决定；
- Risk、Audit和Portfolio统一；
- Evidence Pack支持受限离线验收。
