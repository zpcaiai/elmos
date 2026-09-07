---
name: business-continuity-crisis-dr-and-resilience-coordinator
description: 管理BIA、连续性策略、危机角色、DR计划、演练、供应商和恢复证据。
---

# Business Continuity

## BIA对象

Business Process
Business Service
Site
Data
People
Supplier
Technology
Manual Alternative

## BIA字段

Impact
Maximum Tolerable Period
Minimum Service Level
RTO
RPO
Critical Period
Dependencies
Manual Workaround
Owner

## Continuity Strategy

ACTIVE_ACTIVE
ACTIVE_PASSIVE
WARM_STANDBY
PILOT_LIGHT
BACKUP_RESTORE
MANUAL_OPERATION
ALTERNATE_SUPPLIER
ALTERNATE_SITE
DEGRADED_SERVICE

## Crisis角色

Crisis Commander
Business Lead
Technology Lead
Communications
Security
Legal／Compliance候选
Supplier Lead
Recovery Lead

## DR对象

Application
Database
Identity
Network
DNS
Artifact
Secret
Certificate
Observability
Access
Runbook

## Exercise

TABLETOP
TECHNICAL_FAILOVER
RESTORE
REGION_FAILOVER
SUPPLIER_FAILURE
COMMUNICATION
WORKPLACE_LOSS
FULL_BUSINESS_EXERCISE

## Exercise结果

PASS
PASS_WITH_GAPS
FAIL
ABORTED
INCONCLUSIVE

## 实际能力

Documented RTO
Tested RTO
Observed RTO
Documented RPO
Tested RPO
Observed RPO

## Out-of-band

必须准备：

- Communication；
- Access；
- Credential；
- Runbook；
- Contact；
- Decision Authority。

## 验收标准

- BIA高于单一IT资产；
- RTO／RPO由业务批准；
- Manual Alternative可记录；
- 计划与当前拓扑关联；
- 定期演练；
- 实测与文档分开；
- 供应商纳入；
- 草案标准不冒充正式基线。
