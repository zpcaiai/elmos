# Requirements — Billing Rollout and Migration

These requirements are normative. Implementation must update the global traceability file and the skill completion report.

| Requirement | Priority | Statement | Minimum evidence |
|---|---:|---|---|
| EB-18-001 | P0 | 迁移前必须评估旧数据质量并建立异常队列。 | source + test + runtime evidence |
| EB-18-002 | P0 | 旧余额必须通过 opening balance 双分录导入。 | source + test + runtime evidence |
| EB-18-003 | P0 | 每条迁移记录必须保存源 ID、哈希、版本和审批。 | source + test + runtime evidence |
| EB-18-004 | P0 | 上线前必须运行影子评级并解释新旧差异。 | source + test + runtime evidence |
| EB-18-005 | P0 | 双写阶段只能有一个真实收费权威。 | source + test + runtime evidence |
| EB-18-006 | P0 | 按租户风险分波次金丝雀发布。 | source + test + runtime evidence |
| EB-18-007 | P1 | 重复收费、负余额、预算突破、差异超阈和 SLO 失败必须自动回滚。 | source + test + runtime evidence |
| EB-18-008 | P1 | 切换窗口必须执行最终增量迁移和三方对账。 | source + test + runtime evidence |
| EB-18-009 | P1 | 必须提供客户通知、客服手册和争议快速通道。 | source + test + runtime evidence |
| EB-18-010 | P1 | 旧系统退役前必须保留只读、审计和回退能力。 | source + test + runtime evidence |

## Acceptance semantics

- `IMPLEMENTED`: production code exists, tests pass, runtime evidence exists, and the change is traceable to a commit or current worktree.
- `PARTIAL`: some behavior exists, but at least one acceptance condition, edge case, migration, test, or evidence item is missing.
- `STUB`: interface, placeholder, feature flag, mock, or TODO exists without the required behavior.
- `MISSING`: no meaningful implementation exists.
- `NOT VERIFIED`: implementation may exist, but the agent did not obtain sufficient executable evidence.

## Mandatory trace chain

`Requirement → source file → exact symbol → test → runtime/reconciliation evidence → commit`

Do not collapse multiple unrelated requirements into one vague evidence statement.
