---
name: application-portfolio-inventory-health-fit-and-lifecycle-manager
description: 建立应用组合、Owner、成本、使用、业务适配、技术健康、风险和生命周期决定。
---

# Application Portfolio Management

## Application层级

Product
Application
Application Service
Application Version
Application Instance
Environment

不能把每个Pod或VM都当作独立Application。

## Portfolio数据

Business Capability
Business Owner
Technical Owner
Users
Usage
Revenue Support
Criticality
Cost
Technology
Data
Integration
Vendor
Contract
Lifecycle
Incidents
Security
Change

## Assessment维度

BUSINESS_FIT
FUNCTIONAL_FIT
TECHNICAL_HEALTH
OPERATIONAL_HEALTH
SECURITY
COMPLIANCE
DATA
INTEGRATION
COST_EFFICIENCY
CHANGE_AGILITY
VENDOR
SKILLS

## Evidence Confidence

HIGH
MODERATE
LOW
UNKNOWN

低Confidence不能生成不可逆退役决定。

## 生命周期决定

INVEST
MODERNIZE
MIGRATE
CONSOLIDATE
CONTAIN
REPLACE
RETIRE_CANDIDATE
RETIRE_APPROVED
RETIRED
UNKNOWN

## 重复应用

Duplicate Candidate基于：

- Capability；
- Users；
- Data；
- Process；
- Region；
- Features；
- Contract；
- Runtime。

同一Capability存在多个应用不一定是重复。

## Cost

记录：

License
Infrastructure
Support
Labor
Vendor
Change
Incident
Data
Exit
Allocated Shared Cost

## 退役

必须关联：

Replacement
Data Plan
Consumer Plan
User Plan
Contract Plan
Archive
Identity
Infrastructure
Owner Approval

## 验收标准

- Application与Instance分开；
- 评分可追溯；
- Usage有时间窗口；
- Seasonal和Standby分开；
- 重复只是候选；
- Cost覆盖退出成本；
- 退役需要替代与数据计划。
