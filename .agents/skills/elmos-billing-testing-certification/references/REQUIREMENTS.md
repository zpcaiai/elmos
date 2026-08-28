# Requirements — Billing Testing and Production Certification

These requirements are normative. Implementation must update the global traceability file and the skill completion report.

| Requirement | Priority | Statement | Minimum evidence |
|---|---:|---|---|
| EB-17-001 | P0 | 每条 P0/P1 需求必须关联测试和证据。 | source + test + runtime evidence |
| EB-17-002 | P0 | 账本平衡、非负余额、幂等、cap 和退款上限必须使用属性测试。 | source + test + runtime evidence |
| EB-17-003 | P0 | API、事件和迁移必须使用契约测试。 | source + test + runtime evidence |
| EB-17-004 | P0 | 必须测试高并发预留、重复事件、迟到用量和崩溃恢复。 | source + test + runtime evidence |
| EB-17-005 | P0 | 必须使用支付 sandbox 和结算样本验证。 | source + test + runtime evidence |
| EB-17-006 | P0 | 必须执行跨租户、权限、密钥、重放、注入和欺诈测试。 | source + test + runtime evidence |
| EB-17-007 | P1 | 旧新系统影子账单差异必须可解释并在阈值内。 | source + test + runtime evidence |
| EB-17-008 | P1 | 采用 E1-E5 分级生产认证。 | source + test + runtime evidence |
| EB-17-009 | P1 | P0 缺陷和关键不变量失败必须阻断发布。 | source + test + runtime evidence |
| EB-17-010 | P1 | 认证报告必须机器可读、可复核并关联提交和环境。 | source + test + runtime evidence |

## Acceptance semantics

- `IMPLEMENTED`: production code exists, tests pass, runtime evidence exists, and the change is traceable to a commit or current worktree.
- `PARTIAL`: some behavior exists, but at least one acceptance condition, edge case, migration, test, or evidence item is missing.
- `STUB`: interface, placeholder, feature flag, mock, or TODO exists without the required behavior.
- `MISSING`: no meaningful implementation exists.
- `NOT VERIFIED`: implementation may exist, but the agent did not obtain sufficient executable evidence.

## Mandatory trace chain

`Requirement → source file → exact symbol → test → runtime/reconciliation evidence → commit`

Do not collapse multiple unrelated requirements into one vague evidence statement.
