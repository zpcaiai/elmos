# Requirements — Task Cost and Runtime Estimation

These requirements are normative. Implementation must update the global traceability file and the skill completion report.

| Requirement | Priority | Statement | Minimum evidence |
|---|---:|---|---|
| EB-06-001 | P0 | 执行前必须估算模型、缓存、沙箱、测试、存储、网络和工具资源。 | source + test + runtime evidence |
| EB-06-002 | P0 | 输出 P50/P80/P90 成本区间而非只有单点报价。 | source + test + runtime evidence |
| EB-06-003 | P0 | 输出 Elmos 自主执行机器墙钟 ETA。 | source + test + runtime evidence |
| EB-06-004 | P0 | 人工开发时间必须作为独立比较字段且不得混入系统 ETA。 | source + test + runtime evidence |
| EB-06-005 | P0 | 支持 Economy、Balanced、Best Quality 三种模型策略比较。 | source + test + runtime evidence |
| EB-06-006 | P0 | 估算必须包含风险因素、置信度和主要不确定性来源。 | source + test + runtime evidence |
| EB-06-007 | P1 | 低样本和模型漂移时必须回退到保守规则模型。 | source + test + runtime evidence |
| EB-06-008 | P1 | 历史任务特征使用必须满足租户隔离和匿名化策略。 | source + test + runtime evidence |
| EB-06-009 | P1 | 任务结束后必须记录预测与实际偏差供校准。 | source + test + runtime evidence |
| EB-06-010 | P1 | 估算版本和输入快照必须可复现且不可回写。 | source + test + runtime evidence |

## Acceptance semantics

- `IMPLEMENTED`: production code exists, tests pass, runtime evidence exists, and the change is traceable to a commit or current worktree.
- `PARTIAL`: some behavior exists, but at least one acceptance condition, edge case, migration, test, or evidence item is missing.
- `STUB`: interface, placeholder, feature flag, mock, or TODO exists without the required behavior.
- `MISSING`: no meaningful implementation exists.
- `NOT VERIFIED`: implementation may exist, but the agent did not obtain sufficient executable evidence.

## Mandatory trace chain

`Requirement → source file → exact symbol → test → runtime/reconciliation evidence → commit`

Do not collapse multiple unrelated requirements into one vague evidence statement.
