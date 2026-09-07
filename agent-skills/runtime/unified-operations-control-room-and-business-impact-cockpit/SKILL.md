---
name: unified-operations-control-room-and-business-impact-cockpit
description: 建立面向服务、业务影响、Incident、Change、SLO、容量和连续性的统一运维驾驶舱。
---

# Operations Cockpit

## 视图

EXECUTIVE
SERVICE_OWNER
INCIDENT_COMMAND
ONCALL
PLATFORM
BUSINESS
SECURITY
CAPACITY
CONTINUITY
SUPPLIER

## Executive

显示：

Business Services at Risk
Current Major Incidents
Customer Impact
SLO Status
Error Budget
Critical Capacity
Continuity Risk
Trend

## Incident Command

显示：

Impact
Roles
Timeline
Current Hypothesis
Actions
Changes
Topology
Communication
Next Update
Rollback

## Service Owner

显示：

Service Health
Dependencies
Deployments
Incidents
Problems
SLO
Cost
Capacity
Known Errors
Readiness

## Business Impact

Technical Signal
→ Service Instance
→ Application Service
→ Business Service
→ Customer / Process

## 数据状态

FRESH
DELAYED
PARTIAL
STALE
UNKNOWN

Dashboard不得隐藏数据缺失。

## Drill-down

Business Service
→ SLO
→ Journey
→ Dependency
→ Instance
→ Event
→ Trace / Log / Metric

## War Room

支持：

- 角色；
- 时间线；
- Action；
- Evidence；
- Chat Integration；
- Status Update；
- Decision Log。

## 验收标准

- Dashboard按角色设计；
- 业务和技术可关联；
- 数据新鲜度可见；
- Major Incident有Command View；
- 可从业务下钻至Telemetry；
- 不以单一“红绿灯”掩盖未知；
- Cockpit不成为新的手工数据孤岛。
