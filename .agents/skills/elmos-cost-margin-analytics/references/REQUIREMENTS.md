# Requirements — Cost Allocation and Margin Analytics

These requirements are normative. Implementation must update the global traceability file and the skill completion report.

| Requirement | Priority | Statement | Minimum evidence |
|---|---:|---|---|
| EB-13-001 | P0 | 成本和收入分析必须来源于账本、发票、支付和用量事实。 | source + test + runtime evidence |
| EB-13-002 | P0 | 区分 posted、pending、estimated 和 recognized 状态。 | source + test + runtime evidence |
| EB-13-003 | P0 | 共享成本分摊必须版本化且总额守恒。 | source + test + runtime evidence |
| EB-13-004 | P0 | 支持任务、项目、租户、计划、模型、供应商和时间维度毛利。 | source + test + runtime evidence |
| EB-13-005 | P0 | 计算报价 P50/P80/P90 与实际偏差。 | source + test + runtime evidence |
| EB-13-006 | P0 | 衡量缓存、路由、重试、测试和自动修复的成本影响。 | source + test + runtime evidence |
| EB-13-007 | P1 | 所有总额必须声明 as-of、封账和覆盖范围。 | source + test + runtime evidence |
| EB-13-008 | P1 | 亏损、毛利下降、费率漂移和退款异常必须告警。 | source + test + runtime evidence |
| EB-13-009 | P1 | 分析层不得直接修改交易事实。 | source + test + runtime evidence |
| EB-13-010 | P1 | 价格建议必须通过审批后才能进入价格簿。 | source + test + runtime evidence |

## Acceptance semantics

- `IMPLEMENTED`: production code exists, tests pass, runtime evidence exists, and the change is traceable to a commit or current worktree.
- `PARTIAL`: some behavior exists, but at least one acceptance condition, edge case, migration, test, or evidence item is missing.
- `STUB`: interface, placeholder, feature flag, mock, or TODO exists without the required behavior.
- `MISSING`: no meaningful implementation exists.
- `NOT VERIFIED`: implementation may exist, but the agent did not obtain sufficient executable evidence.

## Mandatory trace chain

`Requirement → source file → exact symbol → test → runtime/reconciliation evidence → commit`

Do not collapse multiple unrelated requirements into one vague evidence statement.
