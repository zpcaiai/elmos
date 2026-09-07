# Requirements — Plan Catalog and Entitlements

These requirements are normative. Implementation must update the global traceability file and the skill completion report.

| Requirement | Priority | Statement | Minimum evidence |
|---|---:|---|---|
| EB-03-001 | P0 | 支持 Free、Pro、Builder、Team、Enterprise 等配置化套餐。 | source + test + runtime evidence |
| EB-03-002 | P0 | 套餐必须支持席位、并发任务、模型等级、保留期、存储和功能权益。 | source + test + runtime evidence |
| EB-03-003 | P0 | 包含额度必须区分付费来源和促销来源。 | source + test + runtime evidence |
| EB-03-004 | P0 | 升级、降级、取消、暂停、重启和试用必须具有确定状态机。 | source + test + runtime evidence |
| EB-03-005 | P0 | 企业合同覆盖必须高于公共套餐且完整审计。 | source + test + runtime evidence |
| EB-03-006 | P0 | 所有服务必须通过统一 entitlement API 判断权限。 | source + test + runtime evidence |
| EB-03-007 | P1 | 权益快照必须绑定计划版本并可历史回放。 | source + test + runtime evidence |
| EB-03-008 | P1 | 并发限制必须在竞争条件下原子执行。 | source + test + runtime evidence |
| EB-03-009 | P1 | 套餐缓存必须由版本事件精确失效。 | source + test + runtime evidence |
| EB-03-010 | P1 | 订阅状态变化不得重复发放额度或重复计费。 | source + test + runtime evidence |

## Acceptance semantics

- `IMPLEMENTED`: production code exists, tests pass, runtime evidence exists, and the change is traceable to a commit or current worktree.
- `PARTIAL`: some behavior exists, but at least one acceptance condition, edge case, migration, test, or evidence item is missing.
- `STUB`: interface, placeholder, feature flag, mock, or TODO exists without the required behavior.
- `MISSING`: no meaningful implementation exists.
- `NOT VERIFIED`: implementation may exist, but the agent did not obtain sufficient executable evidence.

## Mandatory trace chain

`Requirement → source file → exact symbol → test → runtime/reconciliation evidence → commit`

Do not collapse multiple unrelated requirements into one vague evidence statement.
