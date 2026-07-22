---
name: postgresql-domain-model-outbox-and-audit
description: "建立PostgreSQL领域Schema、RLS、Outbox、审计、分区和Migration。"
---

# Schemas

iam
catalog
snapshot
assessment
migration
execution
agent
evidence
delivery
policy
audit
projection

## Outbox

每次业务状态变化：

Business Transaction
+ Outbox Event

同一事务提交。

## Audit

Actor
Tenant
Action
Resource
Before候选
After候选
Decision
Request
IP候选
Time

## Partition

audit_events
execution_logs
usage_records

按月分区候选。

## 验收标准

- 所有Migration可正向执行；
- RLS默认拒绝；
- Outbox无丢事件；
- Audit不可由普通用户删除；
- 乐观锁覆盖项目状态；
- 数据库恢复演练通过。
