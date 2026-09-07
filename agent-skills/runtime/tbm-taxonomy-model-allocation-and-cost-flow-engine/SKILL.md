---
name: tbm-taxonomy-model-allocation-and-cost-flow-engine
description: "将企业财务和技术数据映射到TBM Taxonomy，并执行成本流、共享成本和消费驱动分配。"
---

# TBM Cost Model

## Taxonomy Layer

Cost Source
Cost Pool
Resource Tower
Subtower
Application / Solution
Service / Product
Consumer

## 映射状态

EXACT
RULE_BASED
DERIVED
MANUAL
PARTIAL
UNKNOWN

## Allocation方法

DIRECT
TAG
ACCOUNT
RESOURCE_USAGE
TRANSACTION
USER
SEAT
REVENUE
HEADCOUNT
SERVICE_CONSUMPTION
EVEN_SPREAD
WEIGHTED
ACTIVITY_BASED
KEEP_SHARED
UNALLOCATED

## Allocation Driver

Driver Name
Source
Unit
Period
Coverage
Quality
Owner
Fallback

## Shared Cost

例如：

Identity
Network
Security
Platform
Observability
Enterprise License
Support
Data Center Facility

## Cost Flow

Source Cost
→ Cost Pool
→ Resource
→ Application
→ Service
→ Product
→ Consumer

每一步保存：

Input
Rule
Driver
Output
Residual
Rounding
Evidence

## Rounding

小额Rounding Difference：

- 保留；
- 进入指定Pool；
- 不得静默丢失。

## Reconciliation

必须满足：

Source Total
=
Allocated Total
+ Shared Total
+ Unallocated Total
+ Approved Adjustment

## 验收标准

- 支持TBM 5.0.1 Provider；
- 每层映射可追踪；
- Shared和Unallocated分开；
- Driver有质量；
- 分配结果可重算；
- 总金额可核对；
- 模型版本不可覆盖。
