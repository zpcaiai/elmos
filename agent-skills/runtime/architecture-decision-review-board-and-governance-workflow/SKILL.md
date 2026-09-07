---
name: architecture-decision-review-board-and-governance-workflow
description: 管理ADR、Option、Criterion、Review、批准、后果、Supersede和分级架构治理。
---

# Architecture Decision

## Decision层级

TEAM
PRODUCT
DOMAIN
PLATFORM
ENTERPRISE
REGULATORY

## ADR字段

Title
Context
Concern
Scope
Assumptions
Constraints
Options
Criteria
Decision
Consequences
Risks
Evidence
Owner
Date

## Status

PROPOSED
UNDER_REVIEW
ACCEPTED
ACCEPTED_WITH_CONDITIONS
REJECTED
DEFERRED
SUPERSEDED
DEPRECATED
REVOKED

## Decision Option

Description
Benefits
Costs
Risks
Dependencies
Reversibility
Evidence
Unknowns

## Review模型

ASYNC_REVIEW
DOMAIN_REVIEW
ARCHITECTURE_FORUM
HIGH_RISK_BOARD
EXECUTIVE_DECISION
EXTERNAL_APPROVAL

## Architecture Board

Board只聚焦：

- 跨Domain；
- 战略投资；
- 企业标准；
- 核心数据；
- 高风险；
- 不可逆；
- 大型例外。

## Condition

例如：

- 必须先完成Pilot；
- 限定两个地区；
- 三个月后复核；
- 建立Exit Plan；
- 完成安全评测。

## Supersede

新Decision必须引用：

- 被替代Decision；
- 影响对象；
- 迁移要求；
- 旧标准和例外。

## Decision Implementation

状态：

NOT_STARTED
PARTIALLY_IMPLEMENTED
IMPLEMENTED
DIVERGED
REVERSED
UNKNOWN

## 验收标准

- Decision在实施前或实施中记录；
- Context和Option完整；
- 简单Decision轻量化；
- 高风险Decision分级Review；
- Conditions可监控；
- Supersede可传播；
- 实现状态可验证；
- ADR不允许事后伪造时间。
