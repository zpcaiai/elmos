# Requirements — Elmos Billing Orchestrator

These requirements are normative. Implementation must update the global traceability file and the skill completion report.

| Requirement | Priority | Statement | Minimum evidence |
|---|---:|---|---|
| EB-01-001 | P0 | 扫描并记录现有仓库的计费、任务、支付、模型与租户能力基线。 | source + test + runtime evidence |
| EB-01-002 | P0 | 为每条需求维护五态实施状态并给出可验证证据。 | source + test + runtime evidence |
| EB-01-003 | P0 | 生成无环、可并行且可恢复的批次依赖图。 | source + test + runtime evidence |
| EB-01-004 | P0 | 为长任务保存输入哈希、代码基线、节点进度、输出和成本快照。 | source + test + runtime evidence |
| EB-01-005 | P0 | 支持 Codex 与 Claude Code 在同一证据状态上交接而不重复收费。 | source + test + runtime evidence |
| EB-01-006 | P0 | 禁止跨批次隐式改动公共契约，契约变更必须产生 ADR 和影响分析。 | source + test + runtime evidence |
| EB-01-007 | P1 | 发布门禁必须覆盖安全、账务平衡、对账、性能、恢复和回滚。 | source + test + runtime evidence |
| EB-01-008 | P1 | 完成报告必须关联需求、文件、符号、测试、运行证据和提交。 | source + test + runtime evidence |
| EB-01-009 | P1 | 对固定价范围变化自动生成变更单候选而非继续无界执行。 | source + test + runtime evidence |
| EB-01-010 | P1 | 总体状态必须可由机器从需求和证据文件重新计算。 | source + test + runtime evidence |

## Acceptance semantics

- `IMPLEMENTED`: production code exists, tests pass, runtime evidence exists, and the change is traceable to a commit or current worktree.
- `PARTIAL`: some behavior exists, but at least one acceptance condition, edge case, migration, test, or evidence item is missing.
- `STUB`: interface, placeholder, feature flag, mock, or TODO exists without the required behavior.
- `MISSING`: no meaningful implementation exists.
- `NOT VERIFIED`: implementation may exist, but the agent did not obtain sufficient executable evidence.

## Mandatory trace chain

`Requirement → source file → exact symbol → test → runtime/reconciliation evidence → commit`

Do not collapse multiple unrelated requirements into one vague evidence statement.
