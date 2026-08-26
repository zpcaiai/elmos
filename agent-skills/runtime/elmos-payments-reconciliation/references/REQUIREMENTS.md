# Requirements — Payments and Reconciliation

These requirements are normative. Implementation must update the global traceability file and the skill completion report.

| Requirement | Priority | Statement | Minimum evidence |
|---|---:|---|---|
| EB-10-001 | P0 | 支付层必须通过统一适配器支持多渠道而不污染核心域。 | source + test + runtime evidence |
| EB-10-002 | P0 | 支付密钥必须位于 secret manager 并可轮换。 | source + test + runtime evidence |
| EB-10-003 | P0 | webhook 必须验证签名、时间窗、环境和事件唯一性。 | source + test + runtime evidence |
| EB-10-004 | P0 | 重复、乱序、延迟和缺失 webhook 必须安全处理。 | source + test + runtime evidence |
| EB-10-005 | P0 | 支付成功只能产生一次发票结清或钱包入账。 | source + test + runtime evidence |
| EB-10-006 | P0 | 支持授权、捕获、部分捕获、取消和结算语义。 | source + test + runtime evidence |
| EB-10-007 | P1 | 记录手续费、汇率、净额和到账日期。 | source + test + runtime evidence |
| EB-10-008 | P1 | 每日执行 provider、invoice、ledger 和结算对账。 | source + test + runtime evidence |
| EB-10-009 | P1 | 不一致必须进入 suspense 账户和可分派工作队列。 | source + test + runtime evidence |
| EB-10-010 | P1 | 前端成功页不得作为确认支付的唯一证据。 | source + test + runtime evidence |

## Acceptance semantics

- `IMPLEMENTED`: production code exists, tests pass, runtime evidence exists, and the change is traceable to a commit or current worktree.
- `PARTIAL`: some behavior exists, but at least one acceptance condition, edge case, migration, test, or evidence item is missing.
- `STUB`: interface, placeholder, feature flag, mock, or TODO exists without the required behavior.
- `MISSING`: no meaningful implementation exists.
- `NOT VERIFIED`: implementation may exist, but the agent did not obtain sufficient executable evidence.

## Mandatory trace chain

`Requirement → source file → exact symbol → test → runtime/reconciliation evidence → commit`

Do not collapse multiple unrelated requirements into one vague evidence statement.
