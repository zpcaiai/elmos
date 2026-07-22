---
name: budget-forecast-scenario-and-funding-envelope-manager
description: "管理年度预算、滚动预测、产品资金Envelope、Commitment、Scenario和Variance。"
---

# Financial Planning

## 对象

BUDGET
FORECAST
ACTUAL
COMMITMENT
TARGET
SCENARIO

## Budget类型

COST_CENTER
PRODUCT
PLATFORM
CAPABILITY
PORTFOLIO
REGULATORY
TRANSFORMATION
SHARED_SERVICE

## Forecast

ROLLING_3_MONTH
ROLLING_12_MONTH
QUARTERLY
ANNUAL
LIFECYCLE
CUSTOM

## Forecast Driver

Demand
Usage
Unit Price
Headcount
Vendor
FX
Migration
License
Capacity
Product Roadmap
Risk Event

## Scenario

BASELINE
GROWTH
CONSERVATIVE
ACCELERATED
COST_REDUCTION
VENDOR_EXIT
CLOUD_MIGRATION
PRODUCT_STOP
REGULATORY
INCIDENT

## Funding Envelope

Period
Product
Outcome
Minimum Run
Growth Investment
Debt Investment
Risk Reserve
Contingency
Owner

## Variance

PRICE
VOLUME
MIX
TIMING
FX
ALLOCATION
SCOPE
FORECAST_ERROR
ONE_TIME
UNKNOWN

## Forecast Accuracy

不能通过修改历史Forecast改善。

保存每版Forecast和当时已知假设。

## 验收标准

- Budget、Forecast和Actual分开；
- Commitment纳入；
- Driver可解释；
- Forecast版本不可覆盖；
- Scenario可比较；
- Envelope包含Run和Change；
- Variance有原因；
- Funding与产品Outcome关联。
