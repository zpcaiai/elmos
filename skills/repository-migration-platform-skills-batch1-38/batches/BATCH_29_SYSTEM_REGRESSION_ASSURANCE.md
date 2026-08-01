# Batch 29：System-Wide Regression与Change Impact Assurance

## Goal

建立Requirement、Capability、Journey、Data、Admin、Permission到Test的全局矩阵和变更影响驱动回归。

## Inputs

- Change sets；
- Dependency/evidence graphs；
- Test portfolio；
- Incident history；

## Outputs

- Change impact graph；
- Required test plan；
- Regression evidence；
- Release confidence score；

## Execution Flow

1. 分析代码/Schema/Message/Config/Dependency/Skill影响；
2. 选择Risk-based tests；
3. 创建隔离环境；
4. 执行Golden/历史事故/生产回放/Mixed-version/Rollback回归；
5. 修复并全量确认；

## Verification

- Critical feature均有Regression；
- 测试选择可解释；
- Flaky不被隐藏；
- Release Gate覆盖所有影响；

## Stop Conditions

- 影响图缺关键边；
- Critical测试被优化掉；
- 测试通过但Evidence未更新；

## Gate

`System Regression Gate`

## Installable Skill

`agent-skills/runtime/b29-system-regression-assurance/SKILL.md`
