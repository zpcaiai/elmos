# Batch 10：Test Generation、Mutation、Fuzz、Property、Concurrency与Fault Platform

## Goal

构建多层验证平台，从Source行为、领域不变量和历史事故生成强Oracle、测试、Mutation、Fuzz与Fault场景。

## Inputs

- Source tests/traces；
- Semantic IR；
- Domain invariants；
- Incident corpus；

## Outputs

- Unit/integration/contract/journey tests；
- Mutation packs；
- Fuzz corpus；
- Fault campaigns；
- TQ certificates；

## Execution Flow

1. 恢复Test intent；
2. 生成独立Oracles；
3. 生成Property/Metamorphic tests；
4. 运行Mutation、Fuzz、Schedule和Fault；
5. 将反例固化为Regression；

## Verification

- Critical mutations 100% killed；
- 真实Crash和事故有Regression；
- Flaky失败不隐藏；
- 测试环境可重复；

## Stop Conditions

- 关键行为无可用Oracle；
- 测试只复制Target实现；
- Critical fuzz crash未解决；

## Gate

`TQ1–TQ5`

## Installable Skill

`agent-skills/runtime/b10-test-mutation-fuzz-platform/SKILL.md`
