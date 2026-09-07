---
name: capacity-performance-demand-and-saturation-planner
description: 预测计算、存储、网络、数据库、队列、人力和供应商容量，识别饱和及扩容需求。
---

# Capacity Management

## Resource

CPU
MEMORY
GPU
STORAGE
IOPS
NETWORK
DATABASE_CONNECTION
DATABASE_STORAGE
QUEUE
PARTITION
LICENSE
API_QUOTA
SUPPLIER
ONCALL_CAPACITY

## Demand

User
Transaction
Data
Message
Batch
Model
Region
Season
Campaign
Business Growth
Failure Scenario

## Capacity状态

HEALTHY
ELEVATED
AT_RISK
SATURATED
EXHAUSTED
UNKNOWN

## Forecast

Baseline
Seasonality
Growth
Event
Planned Change
Failure Capacity
Confidence Interval

## Headroom

Normal Headroom
Peak Headroom
Failover Headroom
Maintenance Headroom
Recovery Headroom

## Saturation

CPU高不一定是风险。

需要判断：

- Queue；
- Latency；
- Error；
- Throttling；
- Swap；
- Spill；
- Connection Wait；
- Drop；
- Business Backlog。

## Failure Capacity

必须验证：
