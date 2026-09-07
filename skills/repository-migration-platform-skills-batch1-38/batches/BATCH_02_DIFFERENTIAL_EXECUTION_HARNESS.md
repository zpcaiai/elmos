# Batch 02：Differential Execution Harness与Deterministic Environment

## Goal

建立Source/Target可重复差分执行实验室，统一时间、随机数、调度、外部Provider与状态观察。

## Inputs

- Batch 1基线；
- Source/Target可执行物；
- 测试流量与Fixtures；
- 环境与资源约束；

## Outputs

- Differential execution runtime；
- Deterministic environment profiles；
- Raw/normalized observations；
- Minimal divergence cases；

## Execution Flow

1. 构建隔离Source/Target环境；
2. 注入Virtual Time、Seed与Scheduler；
3. 捕获输出、状态、副作用、错误和资源；
4. 运行差分Oracle；
5. 最小化与重放差异；

## Verification

- 相同Seed结果稳定；
- Normalizer不隐藏关键差异；
- 取消/超时/故障可复现；
- 失败Attempt完整保留；

## Stop Conditions

- Source或Target不可执行；
- 观察盲区覆盖关键副作用；
- 环境差异无法隔离；

## Gate

`B02 Differential Gate`

## Installable Skill

`agent-skills/runtime/b02-differential-execution-harness/SKILL.md`
