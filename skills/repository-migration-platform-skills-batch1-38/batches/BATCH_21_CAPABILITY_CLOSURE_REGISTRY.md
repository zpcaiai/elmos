# Batch 21：System Capability Closure Registry

## Goal

建立Source–Target全功能总账，把Requirement、业务、API、页面、管理端、数据、测试、Metric和Runbook统一映射。

## Inputs

- Requirements；
- Source/Target inventories；
- UI/API/data/admin assets；

## Outputs

- Capability registry；
- Closure maps；
- Missing/orphan/duplicate findings；
- Capability Closure Score；

## Execution Flow

1. 发现Source能力；
2. 建立Target映射；
3. 绑定全层资产；
4. 检查CRUD/取消/补偿/归档生命周期；
5. 检测孤立与缺失；
6. 生成完整性Gate；

## Verification

- 关键能力映射100%；
- Orphan API/UI/Data为零；
- 每项能力有Owner/Test/Metric/Runbook；

## Stop Conditions

- Source关键能力无法解释；
- Target能力无入口或无实现；
- 重复权威能力；

## Gate

`Capability Closure Gate`

## Installable Skill

`agent-skills/runtime/b21-capability-closure-registry/SKILL.md`
