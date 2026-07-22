---
name: organization-team-role-capability-and-work-discovery
description: "发现组织单元、产品、团队、角色、实际工作、责任、决策权和人员配置。"
---

# Organization Discovery

## 数据来源

HRIS
Organization Chart
Product Catalog
Portfolio
Cost Center
Service Catalog
Team Directory
Role Description
On-call
Workflow
Project Plan
Vendor Register
Owner Interview

## 对象

Organization Unit
Product
Team
Role
Position
Person Assignment
Work
Task
Decision Right
Owner
Vendor

## Team状态

ACTIVE
FORMING
TRANSITIONING
TEMPORARY
DISSOLVING
DORMANT
UNKNOWN

## Team类型候选

STREAM_ALIGNED
PLATFORM
ENABLING
COMPLICATED_SUBSYSTEM
FUNCTIONAL
PROJECT
SHARED_SERVICE
OPERATIONS
GOVERNANCE
COMMUNITY
UNKNOWN

## Actual Work

通过批准的数据识别：

- Build；
- Run；
- Support；
- Change；
- Review；
- Approval；
- Incident；
- Coordination；
- Manual Work；
- Vendor Management。

## Declared vs Observed

DECLARED_ONLY
OBSERVED
OWNER_CONFIRMED
CONFLICTED
UNKNOWN

## Findings

UNKNOWN_TEAM_MISSION
UNKNOWN_PRODUCT_OWNER
PROJECT_TEAM_PERMANENT_WORK
TEAM_WITHOUT_STABLE_WORK
PERSON_WITHOUT_ROLE
ROLE_WITHOUT_ACCOUNTABILITY
DUPLICATE_OWNER
HIDDEN_VENDOR_TEAM
EXCESSIVE_PART_TIME_ASSIGNMENT

## 输出

organization-estate.json
team-inventory.json
role-inventory.json
work-inventory.json
decision-rights.json
team-product-map.json
organization-unknowns.json

## 验收标准

- Org Unit、Team和Product分开；
- Person和Role分开；
- 正式工作与实际工作可比较；
- Vendor Team进入同一图；
- Decision Right明确；
- 数据不用于个人绩效评分；
- Unknown Owner进入风险。
