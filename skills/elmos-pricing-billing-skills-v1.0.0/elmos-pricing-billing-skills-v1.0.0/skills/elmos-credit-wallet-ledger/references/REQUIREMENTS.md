# Requirements — Credit Wallet and Double-Entry Ledger

These requirements are normative. Implementation must update the global traceability file and the skill completion report.

| Requirement | Priority | Statement | Minimum evidence |
|---|---:|---|---|
| EB-04-001 | P0 | 所有额度和金额变化必须通过追加式双分录账本。 | source + test + runtime evidence |
| EB-04-002 | P0 | 支持 paid、promotional、reserved、consumed、refunded 和 expired 余额语义。 | source + test + runtime evidence |
| EB-04-003 | P0 | 支持 reserve、capture、partial capture、release、credit、refund 和 adjustment。 | source + test + runtime evidence |
| EB-04-004 | P0 | 每个财务写操作必须提供幂等键并在租户内唯一。 | source + test + runtime evidence |
| EB-04-005 | P0 | 非授信账户不得出现负可用余额。 | source + test + runtime evidence |
| EB-04-006 | P0 | 账本交易必须通过事务性 outbox 发布事件。 | source + test + runtime evidence |
| EB-04-007 | P1 | 余额投影必须可从账本确定性重建。 | source + test + runtime evidence |
| EB-04-008 | P1 | 人工调整必须双人审批并附原因与证据。 | source + test + runtime evidence |
| EB-04-009 | P1 | 赠送额度到期不得改变付费额度法律/会计属性。 | source + test + runtime evidence |
| EB-04-010 | P1 | 账本必须支持日终余额和外部支付对账。 | source + test + runtime evidence |

## Acceptance semantics

- `IMPLEMENTED`: production code exists, tests pass, runtime evidence exists, and the change is traceable to a commit or current worktree.
- `PARTIAL`: some behavior exists, but at least one acceptance condition, edge case, migration, test, or evidence item is missing.
- `STUB`: interface, placeholder, feature flag, mock, or TODO exists without the required behavior.
- `MISSING`: no meaningful implementation exists.
- `NOT VERIFIED`: implementation may exist, but the agent did not obtain sufficient executable evidence.

## Mandatory trace chain

`Requirement → source file → exact symbol → test → runtime/reconciliation evidence → commit`

Do not collapse multiple unrelated requirements into one vague evidence statement.
