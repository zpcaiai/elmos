# Requirements — Usage Metering and Cost Events

These requirements are normative. Implementation must update the global traceability file and the skill completion report.

| Requirement | Priority | Statement | Minimum evidence |
|---|---:|---|---|
| EB-05-001 | P0 | 统一计量模型 Token、缓存、CPU/GPU、浏览器、测试、存储、网络和第三方工具。 | source + test + runtime evidence |
| EB-05-002 | P0 | 用量事件必须不可变并带源事件 ID、时间、租户、任务、运行和节点关联。 | source + test + runtime evidence |
| EB-05-003 | P0 | 重复事件不得产生重复成本或重复扣费。 | source + test + runtime evidence |
| EB-05-004 | P0 | 原始单位必须归一化并保留转换精度和原始值。 | source + test + runtime evidence |
| EB-05-005 | P0 | 内部成本必须绑定事件时点的供应商费率版本。 | source + test + runtime evidence |
| EB-05-006 | P0 | 区分用户可计费、平台吸收、免费、失败重试和 BYOK 用量。 | source + test + runtime evidence |
| EB-05-007 | P1 | 迟到与修正事件必须在封账规则下可处理。 | source + test + runtime evidence |
| EB-05-008 | P1 | 聚合数据必须可追溯回全部明细事件。 | source + test + runtime evidence |
| EB-05-009 | P1 | 用量管道必须支持背压、重试、死信和重放。 | source + test + runtime evidence |
| EB-05-010 | P1 | 必须与供应商账单和任务运行证据周期对账。 | source + test + runtime evidence |

## Acceptance semantics

- `IMPLEMENTED`: production code exists, tests pass, runtime evidence exists, and the change is traceable to a commit or current worktree.
- `PARTIAL`: some behavior exists, but at least one acceptance condition, edge case, migration, test, or evidence item is missing.
- `STUB`: interface, placeholder, feature flag, mock, or TODO exists without the required behavior.
- `MISSING`: no meaningful implementation exists.
- `NOT VERIFIED`: implementation may exist, but the agent did not obtain sufficient executable evidence.

## Mandatory trace chain

`Requirement → source file → exact symbol → test → runtime/reconciliation evidence → commit`

Do not collapse multiple unrelated requirements into one vague evidence statement.
