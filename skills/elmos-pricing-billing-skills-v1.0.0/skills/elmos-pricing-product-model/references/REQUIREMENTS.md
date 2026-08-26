# Requirements — Pricing Product Model

These requirements are normative. Implementation must update the global traceability file and the skill completion report.

| Requirement | Priority | Statement | Minimum evidence |
|---|---:|---|---|
| EB-02-001 | P0 | 支持订阅、预充执行额度、按实际消耗、项目封顶价、固定价和企业年度合同。 | source + test + runtime evidence |
| EB-02-002 | P0 | 普通用户侧使用执行额度或货币金额展示，原始 Token 仅作为成本明细。 | source + test + runtime evidence |
| EB-02-003 | P0 | 价格簿必须包含币种、生效区间、状态、审批和不可变版本号。 | source + test + runtime evidence |
| EB-02-004 | P0 | 模型、沙箱、测试、存储、网络和平台编排费率必须独立配置。 | source + test + runtime evidence |
| EB-02-005 | P0 | managed model 与 BYOK 必须使用不同费率组合。 | source + test + runtime evidence |
| EB-02-006 | P0 | 任务类型必须通过确定性规则路由到按量、封顶、固定或合同计费。 | source + test + runtime evidence |
| EB-02-007 | P1 | 项目 SKU 必须声明输入、输出、范围上限、验收和包含修改轮数。 | source + test + runtime evidence |
| EB-02-008 | P1 | 价格实验必须可分桶、可回滚且不得影响历史结算。 | source + test + runtime evidence |
| EB-02-009 | P1 | 示例价格不得在无审批情况下成为生产价格。 | source + test + runtime evidence |
| EB-02-010 | P1 | 所有价格变更必须生成审计记录和下游影响分析。 | source + test + runtime evidence |

## Acceptance semantics

- `IMPLEMENTED`: production code exists, tests pass, runtime evidence exists, and the change is traceable to a commit or current worktree.
- `PARTIAL`: some behavior exists, but at least one acceptance condition, edge case, migration, test, or evidence item is missing.
- `STUB`: interface, placeholder, feature flag, mock, or TODO exists without the required behavior.
- `MISSING`: no meaningful implementation exists.
- `NOT VERIFIED`: implementation may exist, but the agent did not obtain sufficient executable evidence.

## Mandatory trace chain

`Requirement → source file → exact symbol → test → runtime/reconciliation evidence → commit`

Do not collapse multiple unrelated requirements into one vague evidence statement.
