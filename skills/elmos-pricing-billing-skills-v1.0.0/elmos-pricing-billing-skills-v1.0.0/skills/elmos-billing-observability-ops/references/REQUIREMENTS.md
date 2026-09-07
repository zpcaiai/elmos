# Requirements — Billing Observability and Operations

These requirements are normative. Implementation must update the global traceability file and the skill completion report.

| Requirement | Priority | Statement | Minimum evidence |
|---|---:|---|---|
| EB-16-001 | P0 | 报价到退款全链路必须共享关联 ID 和可检索 trace。 | source + test + runtime evidence |
| EB-16-002 | P0 | 必须监控重复、迟到、预算漂移、负余额、账本不平和对账差异。 | source + test + runtime evidence |
| EB-16-003 | P0 | 定义报价、授权、计量、支付、退款和对账 SLO。 | source + test + runtime evidence |
| EB-16-004 | P0 | 严重财务不变量必须触发 kill switch 或只读模式。 | source + test + runtime evidence |
| EB-16-005 | P0 | 卡住 saga、死信和不一致必须进入可分派工作队列。 | source + test + runtime evidence |
| EB-16-006 | P0 | 必须提供安全重放、投影重建和重新对账工具。 | source + test + runtime evidence |
| EB-16-007 | P1 | 恢复前后必须验证账本、幂等和对账不变量。 | source + test + runtime evidence |
| EB-16-008 | P1 | 账本、合同、发票和审计必须纳入备份与灾备。 | source + test + runtime evidence |
| EB-16-009 | P1 | 必须验证 RPO/RTO 并定期演练。 | source + test + runtime evidence |
| EB-16-010 | P1 | 重大事故必须生成时间线、财务影响、根因和防复发证据。 | source + test + runtime evidence |

## Acceptance semantics

- `IMPLEMENTED`: production code exists, tests pass, runtime evidence exists, and the change is traceable to a commit or current worktree.
- `PARTIAL`: some behavior exists, but at least one acceptance condition, edge case, migration, test, or evidence item is missing.
- `STUB`: interface, placeholder, feature flag, mock, or TODO exists without the required behavior.
- `MISSING`: no meaningful implementation exists.
- `NOT VERIFIED`: implementation may exist, but the agent did not obtain sufficient executable evidence.

## Mandatory trace chain

`Requirement → source file → exact symbol → test → runtime/reconciliation evidence → commit`

Do not collapse multiple unrelated requirements into one vague evidence statement.
