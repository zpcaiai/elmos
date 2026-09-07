---
name: strategy-outcome-portfolio-and-transformation-discovery
description: "发现战略、Outcome、Programme、Product、Initiative、资金、Owner、Benefit和现有转型。"
---

# Transformation Discovery

## 来源

Enterprise Strategy
Business Capability
EA Roadmap
Investment Portfolio
Product Portfolio
Programme Portfolio
Project Portfolio
Funding
Benefit Register
Risk Register
Organization Plan

## 对象

Transformation
Programme
Product Change
Initiative
Project
Workstream
Business Change
Technology Change
Organization Change

## Transformation类型

BUSINESS_MODEL
CUSTOMER
OPERATING_MODEL
DIGITAL
TECHNOLOGY
DATA
AI
ERP
WORKFORCE
MERGER_INTEGRATION
REGULATORY
COST
RESILIENCE

## Transformation字段

Purpose
Strategic Outcome
Sponsor
Owner
Scope
Affected Capabilities
Portfolio
Funding
Timeline
Benefits
Change Cohorts
Dependencies
Risk
Exit Criteria

## 重复识别

根据：

Outcome
Capability
Impacted Group
Deliverable
Technology
Product
Funding
Timeline

识别重复Transformation候选。

## 状态

PROPOSED
APPROVED
ACTIVE
AT_RISK
PAUSED
PIVOTING
STOPPING
SUSTAINING
CLOSED
UNKNOWN

## Findings

TRANSFORMATION_WITHOUT_OUTCOME
TRANSFORMATION_WITHOUT_SPONSOR
DUPLICATE_TRANSFORMATION
UNFUNDED_TRANSFORMATION
BENEFIT_OWNER_MISSING
UNKNOWN_AFFECTED_GROUP
UNKNOWN_EXIT_CRITERIA
PORTFOLIO_ORPHAN

## 输出

transformation-estate.json
transformation-portfolio.json
strategy-transformation-map.json
transformation-owner-map.json
transformation-benefit-map.json
transformation-unknowns.json

## 验收标准

- Transformation和Programme分开；
- Initiative关联Outcome；
- Sponsor和Owner分开；
- 重复只生成候选；
- Funding和Benefit可追踪；
- 未知Scope进入风险；
- 历史和活动Transformation分开。
