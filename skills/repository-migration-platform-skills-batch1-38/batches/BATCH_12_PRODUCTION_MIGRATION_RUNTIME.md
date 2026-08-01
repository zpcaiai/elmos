# Batch 12：Shadow、Strangler、Canary、Rollback与E1–E5

## Goal

建立从离线回放、在线Shadow到Strangler、Canary、全量切换和Source退休的安全生产迁移运行时。

## Inputs

- Target release；
- Production traffic profiles；
- Data/message migration state；
- Rollback assets；

## Outputs

- Shadow evidence；
- Routing plans；
- Canary gates；
- Rollback bundles；
- E1–E5 certificates；

## Execution Flow

1. 离线回放；
2. 在线Shadow且隔离副作用；
3. Strangler单Owner路由；
4. Canary与逐步切流；
5. 自动暂停/回滚/对账；
6. Source退休验证；

## Verification

- Shadow不影响Primary；
- 不可逆Effect结构化隔离；
- Canary业务指标通过；
- 应用/数据/消息/Provider回滚均验证；

## Stop Conditions

- 双Primary或无Owner；
- Target提交后盲目回Source；
- 未知Source caller；

## Gate

`E1–E5`

## Installable Skill

`agent-skills/runtime/b12-production-migration-runtime/SKILL.md`
