---
name: technical-debt-exposure-remediation-and-economic-impact
description: "将技术债与Change Delay、Incident、安全、支持、机会成本和整改成本连接，生成经济影响范围。"
---

# Technical Debt Economics

## Debt来源

OBSOLETE_TECHNOLOGY
UNSUPPORTED_VERSION
MONOLITH_COUPLING
SHARED_DATABASE
NO_TEST
MANUAL_DEPLOYMENT
SECURITY_EXCEPTION
DATA_QUALITY
PLATFORM_FRAGMENTATION
VENDOR_LOCK_IN
KNOWLEDGE_CONCENTRATION
ARCHITECTURE_DRIFT

## Debt对象

Debt Item
Affected Product
Affected Capability
Owner
Evidence
Trigger
Current Control
Remediation

## Exposure

REMEDIATION_COST
CHANGE_DELAY
INCIDENT_COST
SECURITY_EXPOSURE
LICENSE_COST
SUPPORT_COST
SKILL_RISK
OPPORTUNITY_COST
MIGRATION_BLOCKER

## 金额状态

OBSERVED
ESTIMATED
RANGE
SCENARIO
UNKNOWN

## Remediation Option

PAY_DOWN
CONTAIN
REFACTOR
REPLATFORM
REPLACE
RETIRE
ACCEPT
MONITOR

## 经济评估

Remediation Cost
Avoided Cost
Risk Reduction
Time to Value
Dependency Unlock
Service Improvement
Option Value

## Priority

Business Criticality
Change Frequency
Incident
Security
End of Support
Strategic Blocker
Cost
Reversibility

## 技术债比率

可以定义组织内部指标，例如：

Debt Remediation Spend
/
Total Product Technology Spend

但不能作为所有产品统一目标。

## 验收标准

- Debt有具体资产；
- 金额显示范围和Confidence；
- 不冒充会计负债；
- Opportunity Cost有假设；
- Remediation存在多个Option；
- 高债务不自动优先；
- 结果连接Portfolio；
- 修复后验证实际改善。
