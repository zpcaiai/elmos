---
name: service-topology-dependency-and-business-service-model
description: 融合声明、发现和运行时证据，构建服务依赖、实例拓扑和业务影响路径。
---

# Service Topology

## Topology层级

Business Capability
→ Business Service
→ Technical Service
→ Application Service
→ Service Instance
→ Workload
→ Resource

## Dependency类型

CALLS
READS
WRITES
PUBLISHES
CONSUMES
AUTHENTICATES_WITH
ROUTES_TO
RUNS_ON
STORES_IN
DEPENDS_ON_VENDOR
DEPENDS_ON_FACILITY

## Evidence

DECLARED
CONFIGURED
DISCOVERED
TRACE_OBSERVED
NETWORK_OBSERVED
LOG_OBSERVED
OWNER_VERIFIED

## Dependency状态

ACTIVE
SEASONAL
STANDBY
OPTIONAL
CRITICAL
DEGRADED
UNKNOWN

## Critical Path

计算：

- User Entry；
- Auth；
- API；
- Service；
- Data；
- Message；
- External Supplier。

## Business Impact

依赖故障关联：

Customer Segment
Revenue
Order
Payment
Production
Employee
Regulation
Region
SLA

## Topology Drift

ADDED_RUNTIME_EDGE
MISSING_DECLARED_EDGE
UNOBSERVED_DECLARED_EDGE
UNKNOWN_EXTERNAL_EDGE
OWNER_CONFLICT
INSTANCE_MISMATCH

## 验收标准

- 业务与技术拓扑分开；
- 依赖带方向；
- Runtime Evidence有窗口；
- Standby关系不误删；
- Business Impact可追踪；
- Topology Drift形成Finding。
