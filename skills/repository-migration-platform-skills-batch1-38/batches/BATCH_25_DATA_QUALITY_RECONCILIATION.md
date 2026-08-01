# Batch 25：Data Quality、Reconciliation与Accounting Integrity

## Goal

保证跨表、跨服务、跨存储、Source–Target和外部Provider的数据正确、一致、及时且可修复。

## Inputs

- Data lineage；
- Domain invariants；
- Source/Target datasets；
- Provider statements；

## Outputs

- Quality rule registry；
- Reconciliation jobs/reports；
- Repair workflows；
- Data Quality SLO；

## Execution Flow

1. 定义Required/Range/Referential/Temporal规则；
2. 执行Count/Hash/Aggregate/Domain对账；
3. 检测Missing/Duplicate/Late/Drift；
4. 分类迁移缺陷；
5. 受控修复并重验；

## Verification

- 金额/账本/库存/Tenant/Safety差异为零；
- 对账可重放；
- 修复有Audit和Rollback；

## Stop Conditions

- 关键差异无法归因；
- 修复绕过Owner/审批；
- 对账只比较行数；

## Gate

`Data Integrity Gate`

## Installable Skill

`agent-skills/runtime/b25-data-quality-reconciliation/SKILL.md`
