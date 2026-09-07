# Batch 16：Target Architecture Search与Migration Planning

## Goal

恢复Source真实架构和硬约束，搜索语言、Framework、数据、消息与部署组合并生成可执行迁移Blueprint。

## Inputs

- Source architecture/evidence；
- Business/technical constraints；
- Team/budget；
- Certification targets；

## Outputs

- Candidate portfolio；
- Pareto frontier；
- ADRs；
- Migration boundaries/waves；
- Task DAG；
- Target Blueprint；
- AP1–AP5；

## Execution Flow

1. 恢复架构和约束；
2. 构建目标搜索空间；
3. 约束求解与多目标优化；
4. Prototype/Simulation；
5. 选择Retain/Rewrite/Wrap/Strangler/Service化；
6. 生成ADRs与可执行计划；

## Verification

- 至少多候选比较；
- 硬约束不可加权抵消；
- 关键路径Prototype；
- 每个Wave有Entry/Exit/Rollback；

## Stop Conditions

- 关键数据无Owner；
- 只按流行度选型；
- Blueprint无法编译为Task DAG；

## Gate

`AP1–AP5`

## Installable Skill

`agent-skills/runtime/b16-architecture-search-planning/SKILL.md`
