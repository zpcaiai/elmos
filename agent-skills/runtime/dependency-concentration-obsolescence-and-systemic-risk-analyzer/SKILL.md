---
name: dependency-concentration-obsolescence-and-systemic-risk-analyzer
description: 分析应用、数据、技术、供应商、License、人员、地域和合同依赖及系统性风险。
---

# Systemic Dependency Analysis

## Dependency类型

APPLICATION
DATA
API
MESSAGE
IDENTITY
INFRASTRUCTURE
PLATFORM
VENDOR
LICENSE
CONTRACT
SKILL
REGION
FACILITY
DEVICE
MANUAL_PROCESS

## Dependency属性

Criticality
Direction
Optionality
Fallback
SLA
Owner
Observed Usage
Seasonality
Replacement
Exit Time

## Concentration

SINGLE_VENDOR
SINGLE_REGION
SINGLE_PLATFORM
SINGLE_DATABASE
SINGLE_IDENTITY
SINGLE_SKILL
SINGLE_SUPPLIER
SINGLE_NETWORK
SINGLE_DATA_OWNER

## Obsolescence

Unsupported Version
End of Support
No Security Patch
No Skills
No Source
No Vendor
Unknown License
Hardware End of Life
Architecture Dead End

## Graph分析

- Single Point；
- Centrality；
- Strongly Connected Component；
- Blast Radius；
- Cascading Failure；
- Cut Set；
- Dependency Depth；
- Migration Bottleneck。

## Systemic Risk

Local Failure
→ Multiple Applications
→ Business Capability
→ Customer Impact

## Risk状态

IDENTIFIED
ANALYZING
MITIGATING
ACCEPTED
MONITORING
RESOLVED
REOPENED

## 验收标准

- 技术和非技术依赖统一；
- Dependency有方向；
- Optional和Critical分开；
- Skill与Contract进入图；
- 循环依赖可识别；
- Blast Radius关联能力；
- Systemic Risk进入Portfolio。
