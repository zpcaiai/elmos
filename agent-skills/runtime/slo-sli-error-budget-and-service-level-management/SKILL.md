---
name: slo-sli-error-budget-and-service-level-management
description: 建立用户导向SLI、SLO、Error Budget、SLA映射和可靠性决策。
---

# Service Level Management

## 指标层

Business KPI
Customer Journey Indicator
SLI
SLO
SLA
Operational Metric

## SLI类型

AVAILABILITY
SUCCESS_RATE
LATENCY
FRESHNESS
DURABILITY
CORRECTNESS
COMPLETENESS
THROUGHPUT
DEADLINE
QUALITY

## Good / Total

例如：

Successful Eligible Requests
/
All Eligible Requests

必须定义：

Eligible
Good
Excluded
Missing Data
Measurement Point

## SLO

Service
SLI
Target
Window
Calendar
Owner
Users
Exclusions
Policy

## Window

ROLLING
CALENDAR
BUSINESS_HOURS
BATCH_CYCLE
PRODUCTION_SHIFT
CUSTOM

## Error Budget

Budget
Consumed
Remaining
Burn Rate
Forecast
Reset
Policy

## Burn状态

HEALTHY
FAST_BURN
SLOW_BURN
EXHAUSTED
UNKNOWN

## Error Budget Policy

可能动作：

- Normal Delivery；
- Extra Review；
- Canary扩大；
- Freeze High-risk；
- Reliability Sprint；
- Capacity；
- Incident Review。

## SLA

SLA可能包含：

- Availability；
- Response；
- Resolution；
- Support；
- Credit；
- Exclusion。

SLO应服务于内部可靠性管理，不必机械等于SLA。

## 验收标准

- SLI面向用户；
- Good／Total明确；
- Missing Data有策略；
- SLO有Owner；
- Error Budget可计算；
- Policy版本化；
- SLA和SLO分开；
- 组件Metric不冒充服务SLI。
