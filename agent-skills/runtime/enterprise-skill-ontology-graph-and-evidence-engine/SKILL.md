---
name: enterprise-skill-ontology-graph-and-evidence-engine
description: "建立版本化技能本体、技能关系、熟练度、Evidence、Role Requirement和Team Coverage。"
---

# Skill Ontology

## Skill类型

KNOWLEDGE
PRACTICAL_SKILL
PROFESSIONAL_SKILL
DOMAIN_SKILL
TOOL_SKILL
LEADERSHIP
WORKPLACE_SKILL
AI_LITERACY
SAFETY
CERTIFIED_QUALIFICATION

## Provider

SFIA_9
NICE_2_2
ENTERPRISE_CUSTOM
VENDOR_FRAMEWORK
INDUSTRY_FRAMEWORK

## Skill关系

BROADER_THAN
NARROWER_THAN
RELATED_TO
PREREQUISITE
ADJACENT_TO
SUPERSEDES
EQUIVALENT_CANDIDATE
REQUIRES
COMPOSED_OF

## Proficiency

Awareness
Foundation
Working
Independent
Advanced
Expert
Strategic

实际Level由企业Profile定义。

## Skill Claim

Person
Skill Version
Proficiency
Context
Evidence
Assessment
Recency
Confidence
Visibility
Consent

## Evidence等级

SELF_DECLARED
MANAGER_CONFIRMED
FORMAL_ASSESSMENT
PRACTICAL_ASSESSMENT
WORK_OBSERVED
PRODUCTION_VERIFIED
EXTERNAL_CREDENTIAL
TEACHING_VERIFIED

## Recency

CURRENT
AGING
STALE
EXPIRED
UNKNOWN

## Team Coverage

Required Skill
Required Level
Minimum People
Current Verified People
Backup People
Vendor Coverage
Gap

## Privacy

禁止：

- 通过私人通信推断Skill；
- 使用代码量确认熟练度；
- 自动降低个人Skill；
- 公开个人低技能列表；
- 超出用途共享Evidence。

## 验收标准

- Skill和Skill Version分开；
- 支持SFIA和NICE映射；
- 熟练度包含Context；
- Evidence和Claim分开；
- Recency可计算；
- Team Coverage聚合；
- Person拥有纠正和申诉机制。
