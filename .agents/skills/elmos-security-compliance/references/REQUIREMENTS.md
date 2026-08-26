# Requirements — Billing Security and Compliance

These requirements are normative. Implementation must update the global traceability file and the skill completion report.

| Requirement | Priority | Statement | Minimum evidence |
|---|---:|---|---|
| EB-15-001 | P0 | 所有账单数据访问必须强制租户隔离。 | source + test + runtime evidence |
| EB-15-002 | P0 | 高风险动作必须采用最小权限、职责分离和双人审批。 | source + test + runtime evidence |
| EB-15-003 | P0 | 支付、BYOK 和供应商密钥必须由 secret manager 托管。 | source + test + runtime evidence |
| EB-15-004 | P0 | 敏感数据必须在传输、静态和备份中加密。 | source + test + runtime evidence |
| EB-15-005 | P0 | 审计日志必须追加、可验证且覆盖授权决定和财务写入。 | source + test + runtime evidence |
| EB-15-006 | P0 | 必须检测充值、退款、并发、账号接管和机器人欺诈。 | source + test + runtime evidence |
| EB-15-007 | P1 | 日志、提示词和分析事件必须脱敏。 | source + test + runtime evidence |
| EB-15-008 | P1 | 支持隐私访问、导出、删除和合法保留例外。 | source + test + runtime evidence |
| EB-15-009 | P1 | 安全策略必须覆盖 API、队列、数据库、缓存、对象存储和分析层。 | source + test + runtime evidence |
| EB-15-010 | P1 | 生产发布前必须通过越权、重放、竞态、注入和密钥泄漏红队测试。 | source + test + runtime evidence |

## Acceptance semantics

- `IMPLEMENTED`: production code exists, tests pass, runtime evidence exists, and the change is traceable to a commit or current worktree.
- `PARTIAL`: some behavior exists, but at least one acceptance condition, edge case, migration, test, or evidence item is missing.
- `STUB`: interface, placeholder, feature flag, mock, or TODO exists without the required behavior.
- `MISSING`: no meaningful implementation exists.
- `NOT VERIFIED`: implementation may exist, but the agent did not obtain sufficient executable evidence.

## Mandatory trace chain

`Requirement → source file → exact symbol → test → runtime/reconciliation evidence → commit`

Do not collapse multiple unrelated requirements into one vague evidence statement.
