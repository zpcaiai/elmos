---
name: change-risk-standard-normal-emergency-and-release-governor
description: 统一代码、配置、数据、基础设施和运营Change，执行风险评估、窗口、审批、验证和PIR。
---

# Change Enablement

## Change对象

CODE
CONFIGURATION
INFRASTRUCTURE
DATABASE
SECURITY
NETWORK
IDENTITY
MODEL
DATA
RUNBOOK
MANUAL_OPERATION
SUPPLIER

## Change类型

AUTOMATED_LOW_RISK
STANDARD
NORMAL
HIGH_RISK
EMERGENCY

## Risk因素

Service Criticality
Blast Radius
Reversibility
Test Evidence
Change Complexity
Data Impact
Security
Recent Incidents
Error Budget
Change Window
Operator Experience
Dependency Count

## Standard Change

要求：

- Versioned Procedure；
- Repeated Success；
- Test；
- Verification；
- Rollback；
- Known Scope；
- Audit。

## Emergency Change

流程：

Declare Emergency
→ Minimum Approval
→ Execute
→ Verify
→ Incident Link
→ Retrospective Review
→ Standardize or Correct

Emergency不能成为绕过治理的普通通道。

## Change Correlation

每个Incident检查：

- 近期Deployment；
- Feature Flag；
- Configuration；
- Database；
- Infrastructure；
- Certificate；
- Supplier Change。

## Change Verification

Technical
SLO
Business
Security
Data
Cost

## PIR

以下情况触发Post Implementation Review：

- Failed；
- Rolled Back；
- Caused Incident；
- Emergency；
- High Risk；
- Unexpected Difference。

## 验收标准

- 所有变化进入统一Change模型；
- 风险决定审批深度；
- 低风险可自动批准；
- Emergency事后Review；
- Change与Incident自动关联；
- Verification高于“任务成功”；
- Failure反馈Change模板。
