# Batch 07：Database、Cache、Search、Object Storage与Messaging Migration

## Goal

迁移权威数据、派生存储与消息系统，保持事务、精度、顺序、幂等、对账与回滚能力。

## Inputs

- Source schemas/data profiles；
- Queries/transactions；
- Message topology；
- Target infrastructure；

## Outputs

- Target schemas/migrations；
- CDC/backfill plans；
- Outbox/inbox；
- Cache/search/object plans；
- DI evidence；

## Execution Flow

1. 恢复数据Owner和不变量；
2. 生成Expand–Contract与Backfill；
3. 迁移Query/Procedure/ORM；
4. 迁移Message schema和Consumer ownership；
5. 运行对账、故障和回滚验证；

## Verification

- 金额/库存/身份数据零差异；
- Outbox/Inbox原子性；
- 消息重放不重复业务Effect；
- Backup/Restore已演练；

## Stop Conditions

- 数据Owner不明；
- 不可逆DDL无计划；
- 跨库事务语义无法保持；

## Gate

`DI1–DI5`

## Installable Skill

`agent-skills/runtime/b07-data-messaging-migration/SKILL.md`
