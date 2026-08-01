# Batch 30：High Availability、Resilience与Disaster Recovery

## Goal

在Service、数据、消息、Worker、Control Plane、Provider和Region故障下维持关键能力并满足RTO/RPO。

## Inputs

- Failure models；
- SLO/RTO/RPO；
- Deployment/data topologies；
- Runbooks；

## Outputs

- HA/DR plans；
- Chaos/failover tests；
- Backup/restore evidence；
- Resilience certificates；

## Execution Flow

1. 建立依赖故障模型；
2. 配置Timeout/Retry/Bulkhead/Circuit breaker；
3. 设计Read-only/Safe mode；
4. 验证各存储和控制面Failover；
5. 执行DR和Failback Game Day；

## Verification

- 无单点关键服务；
- Backup可恢复；
- RTO/RPO实测通过；
- 故障时不扩大权限或重复Effect；

## Stop Conditions

- 故障恢复需未知人工步骤；
- Failover导致双Writer；
- DR环境证书/配置过期；

## Gate

`Resilience & DR Gate`

## Installable Skill

`agent-skills/runtime/b30-ha-resilience-dr/SKILL.md`
