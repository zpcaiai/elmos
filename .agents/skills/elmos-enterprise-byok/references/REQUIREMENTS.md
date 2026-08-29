# Requirements — Enterprise Contracts and BYOK

These requirements are normative. Implementation must update the global traceability file and the skill completion report.

| Requirement | Priority | Statement | Minimum evidence |
|---|---:|---|---|
| EB-12-001 | P0 | 支持年度平台费、承诺用量、超额、私有部署、支持和 SLA 费用。 | source + test + runtime evidence |
| EB-12-002 | P0 | 支持 minimum commit、burn-down、true-up 和续约。 | source + test + runtime evidence |
| EB-12-003 | P0 | BYOK 只存 secret reference，不存明文密钥。 | source + test + runtime evidence |
| EB-12-004 | P0 | BYOK 排除客户自付模型成本但仍计平台与基础设施费用。 | source + test + runtime evidence |
| EB-12-005 | P0 | 支持企业后付信用限额、PO 和账期。 | source + test + runtime evidence |
| EB-12-006 | P0 | 支持成本中心、部门预算、审批和内部 chargeback。 | source + test + runtime evidence |
| EB-12-007 | P1 | 合同覆盖必须版本化并具有确定优先级。 | source + test + runtime evidence |
| EB-12-008 | P1 | 私有部署必须定义计量可信边界和离线补传。 | source + test + runtime evidence |
| EB-12-009 | P1 | SLA 违约必须通过规则化 service credit 处理。 | source + test + runtime evidence |
| EB-12-010 | P1 | 合同变更不得回写历史结算。 | source + test + runtime evidence |

## Acceptance semantics

- `IMPLEMENTED`: production code exists, tests pass, runtime evidence exists, and the change is traceable to a commit or current worktree.
- `PARTIAL`: some behavior exists, but at least one acceptance condition, edge case, migration, test, or evidence item is missing.
- `STUB`: interface, placeholder, feature flag, mock, or TODO exists without the required behavior.
- `MISSING`: no meaningful implementation exists.
- `NOT VERIFIED`: implementation may exist, but the agent did not obtain sufficient executable evidence.

## Mandatory trace chain

`Requirement → source file → exact symbol → test → runtime/reconciliation evidence → commit`

Do not collapse multiple unrelated requirements into one vague evidence statement.
