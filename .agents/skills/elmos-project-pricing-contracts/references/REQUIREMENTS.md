# Requirements — Capped and Fixed-Price Project Contracts

These requirements are normative. Implementation must update the global traceability file and the skill completion report.

| Requirement | Priority | Statement | Minimum evidence |
|---|---:|---|---|
| EB-08-001 | P0 | 支持 discovery、capped-price 和 fixed-price 三类项目合同。 | source + test + runtime evidence |
| EB-08-002 | P0 | 项目必须冻结源仓库、需求、范围、环境和验收基线。 | source + test + runtime evidence |
| EB-08-003 | P0 | 固定价报价必须基于 P80/P90 成本、毛利、验收、支持和风险。 | source + test + runtime evidence |
| EB-08-004 | P0 | 合同必须声明包含修改轮数、排除项和第三方责任边界。 | source + test + runtime evidence |
| EB-08-005 | P0 | 范围变化必须产生 change order 并在批准前隔离执行。 | source + test + runtime evidence |
| EB-08-006 | P0 | 里程碑验收必须关联自动测试和审批证据。 | source + test + runtime evidence |
| EB-08-007 | P1 | 封顶项目实际结算不得超过合同 cap。 | source + test + runtime evidence |
| EB-08-008 | P1 | 未达固定价验收必须进入明确修复、退款、介入或终止路径。 | source + test + runtime evidence |
| EB-08-009 | P1 | 项目必须记录实际成本、确认收入和毛利复盘。 | source + test + runtime evidence |
| EB-08-010 | P1 | 标准化项目 SKU 必须具备机器可验证输入与输出限制。 | source + test + runtime evidence |

## Acceptance semantics

- `IMPLEMENTED`: production code exists, tests pass, runtime evidence exists, and the change is traceable to a commit or current worktree.
- `PARTIAL`: some behavior exists, but at least one acceptance condition, edge case, migration, test, or evidence item is missing.
- `STUB`: interface, placeholder, feature flag, mock, or TODO exists without the required behavior.
- `MISSING`: no meaningful implementation exists.
- `NOT VERIFIED`: implementation may exist, but the agent did not obtain sufficient executable evidence.

## Mandatory trace chain

`Requirement → source file → exact symbol → test → runtime/reconciliation evidence → commit`

Do not collapse multiple unrelated requirements into one vague evidence statement.
