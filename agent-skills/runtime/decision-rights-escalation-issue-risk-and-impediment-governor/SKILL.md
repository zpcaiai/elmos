---
name: decision-rights-escalation-issue-risk-and-impediment-governor
description: "统一管理Decision Rights、Risk、Issue、Assumption、Impediment、升级、时限和实施验证。"
---

# Transformation Governance Objects

## 对象

RISK
ISSUE
ASSUMPTION
DECISION
IMPEDIMENT
DEPENDENCY_EXCEPTION
SCOPE_CHANGE

## Decision类型

STRATEGIC
FUNDING
SCOPE
ARCHITECTURE
BUSINESS_PROCESS
DATA_AUTHORITY
ORGANIZATION
PEOPLE
CUTOVER
RISK_ACCEPTANCE
BENEFIT
STOP_OR_PIVOT

## Decision字段

Context
Options
Recommendation
Evidence
Decision Owner
Consulted
Needed By
Impact of Delay
Reversibility
Conditions

## Decision状态

IDENTIFIED
PREPARING
READY
AWAITING_DECISION
DECIDED
IMPLEMENTING
VERIFIED
SUPERSEDED
EXPIRED

## Escalation

Trigger
Source Level
Target Level
Reason
Deadline
Options
Recommendation
Acknowledgement

## Impediment

LOCAL
CROSS_TEAM
PORTFOLIO
EXECUTIVE
EXTERNAL
REGULATORY

## Aging

测量：

Issue Age
Decision Wait
Assumption Validation Age
Impediment Age
Escalation Response

## No Decision Policy

继续
暂停
升级
使用默认选项
保护性停止

必须预先定义。

## 验收标准

- Risk和Issue分开；
- Decision Owner明确；
- 决策材料包含Options；
- Impact of Delay可见；
- No Decision Policy明确；
- 决定后验证实施；
- Decision Latency进入健康；
- 历史决定不可覆盖。
