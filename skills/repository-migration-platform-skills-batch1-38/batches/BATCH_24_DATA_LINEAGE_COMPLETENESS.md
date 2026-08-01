# Batch 24：End-to-End Data Flow、Lineage与Completeness

## Goal

建立字段级数据目录与从创建、传输、派生到归档和删除的完整Lineage。

## Inputs

- Schemas/data flows；
- APIs/messages/jobs；
- Storage inventories；
- Privacy policies；

## Outputs

- Enterprise data catalog；
- Field-level lineage；
- Ownership/classification；
- Broken/orphan/duplicate-authority findings；

## Execution Flow

1. 发现业务数据对象；
2. 建立API/Message/DB/Cache/Search/Object/CDC链路；
3. 标记Owner和分类；
4. 追踪派生/归档/删除；
5. 验证Lineage完整性；

## Verification

- Critical field lineage完整；
- 无重复权威Owner；
- 数据跨区和保留规则显式；

## Stop Conditions

- 关键字段来源未知；
- 派生Store无Owner；
- 删除范围不可解析；

## Gate

`Data Flow Closure Gate`

## Installable Skill

`agent-skills/runtime/b24-data-lineage-completeness/SKILL.md`
