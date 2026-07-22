---
name: event-observability-correlation-and-noise-reduction
description: 标准化Metric、Log、Trace、Event和Alert，执行去重、抑制、关联、症状检测和噪声治理。
---

# Event Management

## Event Source

METRIC
LOG
TRACE
SECURITY
DEPLOYMENT
CHANGE
INFRASTRUCTURE
DATABASE
NETWORK
BUSINESS
SUPPLIER
USER_REPORT

## Normalized Event

Event ID
Source
Time
Service
Instance
Environment
Type
Severity
State
Attributes
Trace
Change
Topology

## Event状态

OPEN
UPDATED
RECOVERED
EXPIRED
SUPPRESSED
CORRELATED
UNKNOWN

## Correlation

DEDUPLICATE
TIME_WINDOW
TOPOLOGY
TRACE
CHANGE
COMMON_DEPENDENCY
BUSINESS_JOURNEY
PATTERN
CAUSAL_CANDIDATE

## Alert决策

PAGE
TICKET
AUTOMATE
DASHBOARD
SUPPRESS
CORRELATE
NO_ACTION

## Alert质量

Actionable
Urgent
User Impact
SLO Impact
Owner
Runbook
Auto Recovery
False Positive
Duplicate Rate

## Noise指标

Events per Incident
Alerts per Incident
Pages per Incident
Duplicate Rate
Auto-recovered Page
No-action Page
Alert Flap
Stale Alert

## 告警风暴

处理：

- Group；
- Inhibit；
- Suppress Child；
- Identify Common Dependency；
- Protect Pager；
- Preserve Raw Evidence。

## 验收标准

- Event、Alert和Incident分开；
- Page必须可行动；
- Topology进入关联；
- Change进入关联；
- Raw Event不丢失；
- 抑制有期限；
- Alert Noise持续测量。
