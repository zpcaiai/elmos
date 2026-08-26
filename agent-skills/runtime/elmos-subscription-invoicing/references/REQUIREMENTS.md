# Requirements — Subscriptions and Invoicing

These requirements are normative. Implementation must update the global traceability file and the skill completion report.

| Requirement | Priority | Statement | Minimum evidence |
|---|---:|---|---|
| EB-09-001 | P0 | 支持月付、年付、试用、升级、降级、暂停、取消和重新激活。 | source + test + runtime evidence |
| EB-09-002 | P0 | 发票行必须支持套餐、席位、用量、项目、折扣、税和调整。 | source + test + runtime evidence |
| EB-09-003 | P0 | 价格、税务和合同输入必须在发票上形成不可变快照。 | source + test + runtime evidence |
| EB-09-004 | P0 | draft 发票可重算，finalized 发票不可原地修改。 | source + test + runtime evidence |
| EB-09-005 | P0 | 修正必须使用 credit note、void 或 replacement invoice。 | source + test + runtime evidence |
| EB-09-006 | P0 | 续费扣款和包含额度发放必须分别幂等且合计只发生一次。 | source + test + runtime evidence |
| EB-09-007 | P1 | 支持企业后付账期和信用限额。 | source + test + runtime evidence |
| EB-09-008 | P1 | 失败付款必须进入 dunning 流程。 | source + test + runtime evidence |
| EB-09-009 | P1 | 账期边界必须正确处理时区、月末和闰年。 | source + test + runtime evidence |
| EB-09-010 | P1 | 发票必须输出应收、递延和收入确认事件。 | source + test + runtime evidence |

## Acceptance semantics

- `IMPLEMENTED`: production code exists, tests pass, runtime evidence exists, and the change is traceable to a commit or current worktree.
- `PARTIAL`: some behavior exists, but at least one acceptance condition, edge case, migration, test, or evidence item is missing.
- `STUB`: interface, placeholder, feature flag, mock, or TODO exists without the required behavior.
- `MISSING`: no meaningful implementation exists.
- `NOT VERIFIED`: implementation may exist, but the agent did not obtain sufficient executable evidence.

## Mandatory trace chain

`Requirement → source file → exact symbol → test → runtime/reconciliation evidence → commit`

Do not collapse multiple unrelated requirements into one vague evidence statement.
