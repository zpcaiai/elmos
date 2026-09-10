---
name: elmos-assurance-calibration-holdout
description: 正确率校准与隐藏基准治理。用于在现有Elmos中实现本模块及其自动测试；不用于跳过原生验证、改变认证范围或直接生产签发。
---

# 正确率校准与隐藏基准治理

## Mission
在既有Elmos架构内完成此模块的代码、原生集成、负例和证据。优先级 **P1**。本skill不是新的业务canonical route。

## Read first
当前仓库AGENTS.md/CLAUDE.md；本包`CODEX_START_HERE.md`、`docs/00-architecture.md`、`docs/01-contracts-and-states.md`。
安装后的包根为`.elmos/assurance-package-v4.0.0/`。详细任务/验收在同目录implementation.yaml与acceptance.yaml。

## Preconditions
- 历史真实bugs
- 独立标注样本
- 隐藏项目/变异

## Execute
1. 按项目/语言/DB/缺陷族分层，去重/授权/时间分割，hidden与公开训练修复隔离。
2. 分别计算P(PASS|defect)与P(defect|PASS)，列明分母和抽样方案。
3. 零失败报告置信上界及独立同分布假设；同repo相关变异不能充当独立项目数。
4. 阈值由baseline与风险批准，追踪实际escaped critical bugs，不以百万无效case营销。

## Deliver
- `CalibrationDataset`
- `RiskCalibrationReport`
- `ThresholdApproval`

## Acceptance
- Given 100个样本0假通过; verify 不得宣称风险0或99.999%。
- Given 同一bug的1000变体; verify 按cluster解释样本量。
- Given 修复读取hidden全部答案; verify 污染标记并更换holdout。

## Cross-cutting invariants
Inputs from repos/models/runners are untrusted until the authorized validation boundary accepts them.
Do not alter a frozen scope, policy, oracle or denominator to pass tests. Do not accept a PASS flag as evidence.
Bind tenant/project/run and RevisionSet. Keep builder, hidden-test authority, Ethen review and K8 signing separate.
Do not execute external side effects outside the invocation lease; preserve ceilings and revalidate revocation on resume.

## Failure handling
Return a typed finding and retained raw evidence. Missing native dependencies/permissions → NOT_RUN/INCONCLUSIVE, never simulated production success.
Rollback by feature flag or compensating migration; do not erase sealed evidence or revoke history.

## Completion report
List actual files changed, reused modules, commands/exit codes, acceptance IDs and immutable evidence references, blockers and next dependency-ready task.
Documentation and reference tests alone do not finish product implementation.
