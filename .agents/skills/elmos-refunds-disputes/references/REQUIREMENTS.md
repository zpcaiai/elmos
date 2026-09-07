# Requirements — Refunds, Adjustments, and Disputes

These requirements are normative. Implementation must update the global traceability file and the skill completion report.

| Requirement | Priority | Statement | Minimum evidence |
|---|---:|---|---|
| EB-11-001 | P0 | 退款必须基于平台、用户、第三方、范围和验收等责任分类。 | source + test + runtime evidence |
| EB-11-002 | P0 | 平台故障造成且用户未获得价值的消耗必须自动免收或退回。 | source + test + runtime evidence |
| EB-11-003 | P0 | 模型在任务预算内的正常自我修复不得无限追加收费。 | source + test + runtime evidence |
| EB-11-004 | P0 | 退款必须关联原 quote、用量、账本、支付和成果证据。 | source + test + runtime evidence |
| EB-11-005 | P0 | 支持全额、部分、额度补偿、credit note 和 chargeback。 | source + test + runtime evidence |
| EB-11-006 | P0 | 原交易不得删除；退款使用反向交易表达。 | source + test + runtime evidence |
| EB-11-007 | P1 | 累计退款不得超过原可退款基数。 | source + test + runtime evidence |
| EB-11-008 | P1 | 支付退款和钱包回退必须具备 saga 补偿。 | source + test + runtime evidence |
| EB-11-009 | P1 | 大额和人工调整必须双人审批。 | source + test + runtime evidence |
| EB-11-010 | P1 | 退款、争议和对账状态必须完整审计。 | source + test + runtime evidence |

## Acceptance semantics

- `IMPLEMENTED`: production code exists, tests pass, runtime evidence exists, and the change is traceable to a commit or current worktree.
- `PARTIAL`: some behavior exists, but at least one acceptance condition, edge case, migration, test, or evidence item is missing.
- `STUB`: interface, placeholder, feature flag, mock, or TODO exists without the required behavior.
- `MISSING`: no meaningful implementation exists.
- `NOT VERIFIED`: implementation may exist, but the agent did not obtain sufficient executable evidence.

## Mandatory trace chain

`Requirement → source file → exact symbol → test → runtime/reconciliation evidence → commit`

Do not collapse multiple unrelated requirements into one vague evidence statement.
