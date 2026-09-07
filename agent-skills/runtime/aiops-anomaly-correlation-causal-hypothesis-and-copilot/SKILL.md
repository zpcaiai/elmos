---
name: aiops-anomaly-correlation-causal-hypothesis-and-copilot
description: 使用统计、拓扑、历史与模型生成异常、事件聚类、原因假设、相似Incident和运维Copilot建议。
---

# AIOps

## 能力

Anomaly Detection
Event Clustering
Alert Deduplication
Topology Correlation
Change Correlation
Similar Incident
Causal Hypothesis
Runbook Recommendation
Incident Summary
Capacity Forecast
Ticket Classification

## 输入

Metric
Log
Trace
Event
Alert
Topology
Change
Deployment
Incident
Problem
Business KPI
Runbook

## Anomaly

STATIC_THRESHOLD
DYNAMIC_BASELINE
SEASONAL
MULTIVARIATE
CHANGE_POINT
OUTLIER
FORECAST_DEVIATION

## Correlation

TIME
TOPOLOGY
TRACE
CHANGE
COMMON_DEPENDENCY
PATTERN
BUSINESS_JOURNEY

## Hypothesis

Hypothesis
Evidence For
Evidence Against
Affected Path
Confidence
Test
Result

## Confidence

LOW
MODERATE
HIGH
CONFIRMED_BY_EXPERIMENT
DISPROVED

模型Confidence不能自动提升为Confirmed。

## Similar Incident

比较：

Symptoms
Topology
Change
Logs
Service
Impact
Recovery
Root Cause

## Copilot

允许：

- 摘要；
- 查询生成；
- 时间线；
- 相似案例；
- Runbook建议；
- 沟通草稿。

禁止：

- 自行确认Root Cause；
- 未经授权执行生产写；
- 隐藏不确定性；
- 伪造日志；
- 自动关闭Incident。

## 数据治理

Prompt和Context需：

- Redaction；
- Tenant Isolation；
- Secret Filtering；
- Retention；
- Model Policy；
- Audit。

## 验收标准

- AIOps结果有Evidence；
- Hypothesis可证伪；
- 相似案例说明差异；
- Confidence可校准；
- Copilot不直接获得管理员权限；
- 输出不确定性明确；
- Incident结果反馈模型评测。
