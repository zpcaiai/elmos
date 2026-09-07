# Requirements — Quote and Budget Guard

These requirements are normative. Implementation must update the global traceability file and the skill completion report.

| Requirement | Priority | Statement | Minimum evidence |
|---|---:|---|---|
| EB-07-001 | P0 | 报价必须显示费用区间、最大预算、机器墙钟 ETA、人工时间对比和置信度。 | source + test + runtime evidence |
| EB-07-002 | P0 | 报价必须绑定价格簿、估算、模型策略和范围版本。 | source + test + runtime evidence |
| EB-07-003 | P0 | 任务启动前必须原子预留最大预算或验证企业授信。 | source + test + runtime evidence |
| EB-07-004 | P0 | 支持 50%、80%、95% 等可配置预算提醒。 | source + test + runtime evidence |
| EB-07-005 | P0 | 达到硬上限前必须停止新的可计费执行。 | source + test + runtime evidence |
| EB-07-006 | P0 | 支持追加预算、模型降级、范围缩小、仅修阻断项和停止导出。 | source + test + runtime evidence |
| EB-07-007 | P1 | 完成后按实际用量捕获并释放未使用预留。 | source + test + runtime evidence |
| EB-07-008 | P1 | 失败和取消结算必须使用责任与成果规则并可审计。 | source + test + runtime evidence |
| EB-07-009 | P1 | 报价过期或范围改变后必须重新报价。 | source + test + runtime evidence |
| EB-07-010 | P1 | 断线或服务重启后预算状态和任务状态必须一致恢复。 | source + test + runtime evidence |

## Acceptance semantics

- `IMPLEMENTED`: production code exists, tests pass, runtime evidence exists, and the change is traceable to a commit or current worktree.
- `PARTIAL`: some behavior exists, but at least one acceptance condition, edge case, migration, test, or evidence item is missing.
- `STUB`: interface, placeholder, feature flag, mock, or TODO exists without the required behavior.
- `MISSING`: no meaningful implementation exists.
- `NOT VERIFIED`: implementation may exist, but the agent did not obtain sufficient executable evidence.

## Mandatory trace chain

`Requirement → source file → exact symbol → test → runtime/reconciliation evidence → commit`

Do not collapse multiple unrelated requirements into one vague evidence statement.
