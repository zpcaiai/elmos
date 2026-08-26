# Requirements — Billing Customer and Admin UX

These requirements are normative. Implementation must update the global traceability file and the skill completion report.

| Requirement | Priority | Statement | Minimum evidence |
|---|---:|---|---|
| EB-14-001 | P0 | 报价卡必须展示费用区间、cap、机器 ETA、人工对比、模式、测试和验收。 | source + test + runtime evidence |
| EB-14-002 | P0 | 运行页必须展示已用、预留、预计剩余和预算阈值。 | source + test + runtime evidence |
| EB-14-003 | P0 | 支持追加预算、降级、缩小范围、仅修阻断项和停止导出。 | source + test + runtime evidence |
| EB-14-004 | P0 | 钱包必须区分付费、赠送、冻结、已用、退款和到期。 | source + test + runtime evidence |
| EB-14-005 | P0 | 账单与用量必须可下钻到任务、运行、节点和资源。 | source + test + runtime evidence |
| EB-14-006 | P0 | 项目页面必须展示范围基线、里程碑、验收和变更单。 | source + test + runtime evidence |
| EB-14-007 | P1 | 团队必须支持成本中心、部门预算和审批。 | source + test + runtime evidence |
| EB-14-008 | P1 | 高风险后台动作必须预览、二次确认、审批和审计。 | source + test + runtime evidence |
| EB-14-009 | P1 | 所有财务规则必须由后端执行。 | source + test + runtime evidence |
| EB-14-010 | P1 | 关键旅程必须满足无障碍、断线恢复和多币种显示要求。 | source + test + runtime evidence |

## Acceptance semantics

- `IMPLEMENTED`: production code exists, tests pass, runtime evidence exists, and the change is traceable to a commit or current worktree.
- `PARTIAL`: some behavior exists, but at least one acceptance condition, edge case, migration, test, or evidence item is missing.
- `STUB`: interface, placeholder, feature flag, mock, or TODO exists without the required behavior.
- `MISSING`: no meaningful implementation exists.
- `NOT VERIFIED`: implementation may exist, but the agent did not obtain sufficient executable evidence.

## Mandatory trace chain

`Requirement → source file → exact symbol → test → runtime/reconciliation evidence → commit`

Do not collapse multiple unrelated requirements into one vague evidence statement.
